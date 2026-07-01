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
DEBUG_UI = os.environ.get("DEBUG_UI", "").lower() in {"1", "true", "yes", "on"}
ASSISTANT_INSTRUCTIONS = """Du bist der Eden Klima Wissensassistent.
Antworte immer auf Deutsch.
Nutze technische Unterlagen und die Eden Klima Wissensdatenbank, wenn diese Informationen verfügbar sind.
Wenn keine passende Quelle gefunden wird, sage das klar auf Deutsch und gib nur sichere, allgemeine Orientierung.
Erfinde keine Herstellerangaben, Fehlercodes oder Wartungsanweisungen.
Weise bei Arbeiten an Strom, Kältemittel oder sicherheitsrelevanten Bauteilen auf Fachtechniker hin."""

# Populated at startup.
AGENT_ENDPOINT = None
AGENT_API_KEY = None
DISCOVERY_ERROR = None

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
    return {
        "status": "ok",
        "agent_ready": AGENT_ENDPOINT is not None and AGENT_API_KEY is not None,
        "agent_error": DISCOVERY_ERROR,
    }


@app.post("/api/chat")
async def chat(request: Request):
    """Proxy a chat message to the managed agent and return the response."""
    if not AGENT_ENDPOINT or not AGENT_API_KEY:
        return JSONResponse(
            content={
                "error": (
                    "Der Wissensassistent ist noch nicht bereit. "
                    "Bitte prüfen Sie AGENT_UUID, DO_API_TOKEN und die Berechtigungen des DigitalOcean API Tokens."
                ),
                "details": DISCOVERY_ERROR,
            },
        )

    body = await request.json()
    message = body.get("message", "")
    history = body.get("history", [])

    # Build OpenAI-compatible messages array.
    # DigitalOcean agent deployments can return an empty response when a separate
    # system role is sent, so the German guidance is attached to the user turn.
    messages = []
    for h in history:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": f"{ASSISTANT_INSTRUCTIONS}\n\nFrage: {message}"})

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
        if DEBUG_UI:
            content = (
                "Technischer Debug: Der Agent-Dienst hat keine verwertbare Antwort geliefert. "
                f"Status: {resp.status_code}. JSON-Schlüssel: {', '.join(sorted(data.keys())) or 'keine'}."
            )

    sources = _extract_sources(data)

    return JSONResponse(content={"content": content, "usage": data.get("usage"), "sources": sources})


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
