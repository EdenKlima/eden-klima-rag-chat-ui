"""RAG Assistant Chat UI — a lightweight FastAPI app that proxies chat
messages to a DigitalOcean managed GenAI agent and serves a simple web
interface.

The app self-discovers the agent's deployment URL and API key at startup
using the DO API.

Environment variables (injected by terraform via App Platform):
    AGENT_UUID   — UUID of the managed agent
    DO_API_TOKEN — DigitalOcean API token
    AGENT_NAME   — Display name of the agent (optional)
"""

import logging
import os
import sys
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("chat-ui")

app = FastAPI(title="Eden Klima Wissensassistent")

AGENT_UUID = os.environ.get("AGENT_UUID", "")
DO_API_TOKEN = os.environ["DO_API_TOKEN"]
AGENT_NAME = os.environ.get("AGENT_NAME", "Eden Klima Wissensassistent")
DO_API_BASE = os.environ.get("DO_API_BASE", "https://api.digitalocean.com")
DO_STATUS_URL = os.environ.get("DO_STATUS_URL", "https://status.digitalocean.com/api/v2/summary.json")
DO_STATUS_CACHE_SECONDS = 60
MAINTENANCE_MESSAGE = (
    "Der Wissensassistent ist aktuell wegen einer technischen Störung beim KI-Dienst eingeschränkt. "
    "Bitte versuchen Sie es später erneut."
)
DO_RELEVANT_COMPONENTS = {
    "Agentic Inference Cloud",
    "Agent Runtime",
    "Knowledge Bases",
    "Model Services",
    "Guardrails",
    "Inference",
}
# Populated at startup.
AGENT_ENDPOINT = None
AGENT_API_KEY = None
DISCOVERY_ERROR = None
PROVIDER_STATUS_CACHE = {"checked_at": 0.0, "degraded": False, "components": []}

# Serve the static HTML chat page.
INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text()


def _do_headers():
    return {"Authorization": f"Bearer {DO_API_TOKEN}", "Content-Type": "application/json"}


def _discover_agent():
    """Fetch agent details from the DO API to get the deployment URL and API key."""
    global AGENT_ENDPOINT, AGENT_API_KEY

    if not AGENT_UUID:
        raise RuntimeError("AGENT_UUID is not configured")

    logger.info("Discovering agent %s ...", AGENT_UUID)
    with httpx.Client(timeout=30.0) as client:
        # Get agent details.
        resp = client.get(f"{DO_API_BASE}/v2/gen-ai/agents/{AGENT_UUID}", headers=_do_headers())
        resp.raise_for_status()
        agent = resp.json()["agent"]

        # Extract deployment URL.
        deployment = agent.get("deployment", {})
        deploy_url = deployment.get("url")
        if deploy_url:
            AGENT_ENDPOINT = f"{deploy_url}/api/v1/chat/completions"
            logger.info("Agent endpoint: %s", AGENT_ENDPOINT)
        else:
            logger.error("Agent has no deployment URL. Status: %s", deployment.get("status"))
            raise RuntimeError("Agent deployment URL not available")

        # Create an API key for agent authentication.
        # The auto-generated api_keys[].api_key is a chatbot identifier, not a secret key.
        # We need to create a real API key via the API.
        logger.info("Creating agent API key...")
        key_resp = client.post(
            f"{DO_API_BASE}/v2/gen-ai/agents/{AGENT_UUID}/api_keys",
            headers=_do_headers(),
            json={"name": "chat-ui"},
        )
        key_resp.raise_for_status()
        AGENT_API_KEY = key_resp.json()["api_key_info"]["secret_key"]
        logger.info("Agent API key created")


@app.on_event("startup")
async def startup_event():
    global DISCOVERY_ERROR
    try:
        _discover_agent()
        DISCOVERY_ERROR = None
    except Exception as exc:
        DISCOVERY_ERROR = str(exc)
        logger.exception("Agent discovery failed; chat endpoint will report not ready")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat UI."""
    return INDEX_HTML.replace("{{AGENT_NAME}}", AGENT_NAME)


@app.get("/health")
async def health():
    provider_status = await _get_provider_status()
    return {
        "status": "ok",
        "agent_ready": AGENT_ENDPOINT is not None and AGENT_API_KEY is not None,
        "agent_error": DISCOVERY_ERROR,
        "provider_degraded": provider_status["degraded"],
        "provider_components": provider_status["components"],
    }


@app.post("/api/chat")
async def chat(request: Request):
    """Proxy a chat message to the managed agent and return the response."""
    provider_status = await _get_provider_status()
    if provider_status["degraded"]:
        logger.warning("Provider degraded, skipping agent request. Components: %s", provider_status["components"])
        return JSONResponse(
            content={
                "content": MAINTENANCE_MESSAGE,
                "maintenance": True,
                "provider_components": provider_status["components"],
            },
        )

    if not AGENT_ENDPOINT or not AGENT_API_KEY:
        return JSONResponse(
            content={
                "error": "Die Antwort konnte gerade nicht generiert werden. Bitte versuchen Sie es erneut.",
            },
        )

    body = await request.json()
    message = body.get("message", "")
    history = body.get("history", [])

    # Build OpenAI-compatible messages array. Keep the user query clean so the
    # agent's configured instructions and retrieval rewrite work like the DO console.
    messages = []
    for h in history:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    logger.info(
        "Sending request to agent: message_count=%s last_user_message=%r agent_uuid_present=%s",
        len(messages),
        message[-500:],
        bool(AGENT_UUID),
    )

    headers = {
        "Authorization": f"Bearer {AGENT_API_KEY}",
        "Content-Type": "application/json",
    }

    agent_payload = {
        "messages": messages,
        "include_retrieval_info": True,
        "include_guardrails_info": True,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(AGENT_ENDPOINT, json=agent_payload, headers=headers)

    logger.info("Agent response status_code=%s", resp.status_code)

    try:
        data = resp.json()
    except Exception:
        return JSONResponse(status_code=resp.status_code, content={"error": resp.text})

    logger.info("Agent response JSON keys=%s", sorted(data.keys()))

    # Extract the response text from common OpenAI-compatible and agent formats.
    content = _extract_content(data)
    logger.info("Agent assistant content length=%s", len(content))

    if not content:
        logger.warning("Agent returned no response content. Response keys: %s", sorted(data.keys()))
        content = "Die Antwort konnte gerade nicht generiert werden. Bitte versuchen Sie es erneut."

    sources = _extract_sources(data)

    return JSONResponse(content={"content": content, "usage": data.get("usage"), "sources": sources})


async def _get_provider_status():
    now = time.monotonic()
    if now - PROVIDER_STATUS_CACHE["checked_at"] < DO_STATUS_CACHE_SECONDS:
        return PROVIDER_STATUS_CACHE

    degraded = False
    degraded_components = []
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": "eden-klima-rag-chat-ui"}) as client:
            resp = await client.get(DO_STATUS_URL)
            resp.raise_for_status()
            data = resp.json()

        for component in data.get("components", []):
            name = component.get("name", "")
            status = component.get("status", "operational")
            description = component.get("description") or ""
            component_text = f"{name} {description}".lower()
            is_relevant = name in DO_RELEVANT_COMPONENTS or any(
                term.lower() in component_text for term in DO_RELEVANT_COMPONENTS
            )
            if is_relevant and status != "operational":
                degraded = True
                degraded_components.append({"name": name, "status": status})

    except Exception:
        logger.exception("Could not check DigitalOcean provider status; continuing with normal chat flow")
        degraded = False
        degraded_components = []

    PROVIDER_STATUS_CACHE.update(
        {"checked_at": now, "degraded": degraded, "components": degraded_components}
    )
    return PROVIDER_STATUS_CACHE


def _extract_content(data):
    if not isinstance(data, dict):
        return ""

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        message = first.get("message") if isinstance(first, dict) else None
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        if isinstance(first, dict) and first.get("text"):
            return str(first["text"])

    message = data.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])

    for key in ("content", "answer", "response", "output_text"):
        value = data.get(key)
        if value:
            return str(value)

    detail = data.get("detail")
    if detail:
        return f"Fehler: {detail}"

    error = data.get("error")
    if error:
        return str(error)

    return ""


def _extract_sources(data):
    if not isinstance(data, dict):
        return None

    candidates = [
        data.get("sources"),
        data.get("citations"),
        data.get("retrieval_info"),
        data.get("retrievalInfo"),
        data.get("metadata", {}).get("sources") if isinstance(data.get("metadata"), dict) else None,
    ]

    for candidate in candidates:
        if _has_sources(candidate):
            return candidate
    return None


def _has_sources(value):
    if not value:
        return False
    if isinstance(value, list):
        return any(_has_sources(item) for item in value)
    if isinstance(value, dict):
        return any(_has_sources(item) for item in value.values())
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() not in {"{}", "[]", '{"citations":[]}'}
    return False
