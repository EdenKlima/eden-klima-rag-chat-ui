"""RAG Assistant Chat UI — a lightweight FastAPI app that proxies chat
messages to a DigitalOcean managed GenAI agent and serves a simple web
interface.

Error-code questions take a deterministic path: a regex detects the code,
the verified record is loaded from data/error_codes.json and injected into
the agent request, so the answer never depends on vector-search ranking.
All other questions use the agent's knowledge-base retrieval as before.

Endpoints:
    GET  /                     chat UI
    GET  /health               liveness + agent/lookup state
    POST /api/chat             single JSON response
    POST /api/chat/stream      server-sent events (token stream + meta event)
    POST /api/feedback         store a thumbs up/down for an answer
    GET  /api/feedback/summary recent feedback counts (in-memory)

Environment variables:
    AGENT_ENDPOINT   — agent endpoint URL (preferred; base URL or full /api/v1/chat/completions)
    AGENT_ACCESS_KEY — static agent access key (preferred)
    AGENT_UUID       — UUID of the managed agent (legacy discovery fallback)
    DO_API_TOKEN     — DigitalOcean API token (legacy discovery fallback only;
                       creates a new agent key at startup — set AGENT_ENDPOINT +
                       AGENT_ACCESS_KEY instead to stop key minting)
    AGENT_NAME       — display name of the agent (optional)
    LOOKUP_ENABLED   — set to 0 to disable the deterministic error-code path
    STREAMING_ENABLED— set to 0 to disable /api/chat/stream (UI falls back)
    RATE_LIMIT_PER_MINUTE — per-IP request budget, 0 disables (default 30)
"""

import json
import logging
import os
import re
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("chat-ui")

app = FastAPI(title="Eden Klima Wissensassistent")

AGENT_UUID = os.environ.get("AGENT_UUID", "")
DO_API_TOKEN = os.environ.get("DO_API_TOKEN", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "Eden Klima Wissensassistent")
DO_API_BASE = os.environ.get("DO_API_BASE", "https://api.digitalocean.com")
DO_STATUS_URL = os.environ.get("DO_STATUS_URL", "https://status.digitalocean.com/api/v2/summary.json")
DO_STATUS_CACHE_SECONDS = 60
LOOKUP_ENABLED = os.environ.get("LOOKUP_ENABLED", "1") != "0"
STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "1") != "0"
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))
MAX_MESSAGE_CHARS = int(os.environ.get("MAX_MESSAGE_CHARS", "2000"))
MAX_HISTORY_ENTRIES = int(os.environ.get("MAX_HISTORY_ENTRIES", "16"))
AGENT_TIMEOUT_SECONDS = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "90"))

PROVIDER_DEGRADED_HINT = (
    "Beim KI-Dienst gibt es aktuell eine gemeldete Störung. Antworten können unvollständig sein."
)
KB_UNAVAILABLE_MESSAGE = (
    "Die Wissensdatenbank konnte gerade nicht zuverlässig abgefragt werden. "
    "Bitte versuchen Sie es erneut oder kontaktieren Sie Eden Klima."
)
NO_ANSWER_MESSAGE = "Die Antwort konnte gerade nicht generiert werden. Bitte versuchen Sie es erneut."
RATE_LIMIT_MESSAGE = (
    "Es sind gerade sehr viele Anfragen offen. Bitte warten Sie einen Moment und versuchen Sie es erneut."
)
# The platform guardrail replaces blocked answers with canned English text.
GUARDRAIL_CANNED_MARKERS = (
    "I'm not able to respond to that request",
    "I am not able to respond to that request",
    "I can't help with that request",
    "I cannot help with that request",
)
GUARDRAIL_SAFE_MESSAGE = (
    "Zu dieser Anfrage kann ich keine Anleitung geben, da sie sicherheitsrelevante Arbeiten an der "
    "Anlage betreffen kann. Arbeiten an Strom, Kältemittel oder sicherheitsrelevanten Bauteilen "
    "dürfen nur qualifizierte Fachtechniker durchführen. Eden Klima hilft gerne weiter — Wartung "
    "oder Reparatur können Sie unverbindlich über den Preisrechner anfragen: "
    "https://www.eden-klima.at/klimaanlagen-wartung/preisrechner/"
)
DO_RELEVANT_COMPONENTS = {
    "Agentic Inference Cloud",
    "Agent Runtime",
    "Knowledge Bases",
    "Model Services",
    "Guardrails",
    "Inference",
}
# Populated at startup (or from env).
AGENT_ENDPOINT = None
AGENT_API_KEY = None
DISCOVERY_ERROR = None
LAST_DISCOVERY_ATTEMPT = 0.0
DISCOVERY_RETRY_SECONDS = 60
PROVIDER_STATUS_CACHE = {"checked_at": 0.0, "degraded": False, "components": []}

# Serve the static HTML chat page.
INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text()

# ---------------------------------------------------------------------------
# Deterministic error-code lookup
# ---------------------------------------------------------------------------

ERROR_DB_PATH = Path(__file__).parent / "data" / "error_codes.json"
try:
    _db = json.loads(ERROR_DB_PATH.read_text(encoding="utf-8"))
    ERROR_CODES = _db.get("codes", {})
    ERROR_RANGES = _db.get("ranges", [])
except Exception:
    logger.exception("Could not load %s — deterministic lookup disabled", ERROR_DB_PATH)
    ERROR_CODES, ERROR_RANGES = {}, []

ERROR_CODES_SOURCE_LABEL = "Samsung Fehlercode-Datenbank (verifizierter Eintrag)"
KNOWN_GROUPS = ("FJM", "CAC", "DVM", "ERV", "EHS")

# 3-digit code, optional E prefix, not embedded in longer alphanumerics (R410A, AR12…, 2026).
CODE_RE = re.compile(r"(?<![0-9A-Za-z])(?:[eE][-. ]?)?([1-9][0-9]{2})(?![0-9A-Za-z])")
CODE_CONTEXT_RE = re.compile(
    r"(?i)\b(fehl[a-zäöü]*|err?[o0]r[a-z]*|codes?|st(?:ö|oe)rung(?:en)?|meldung|alarm"
    r"|zeigt|angezeigt|anzeige|blinkt|shows?|displays?|displayed)\b"
)
BARE_CODE_RE = re.compile(r"^[eE]?[-. ]?[1-9][0-9]{2}[\s?.!]*$")
CODES_WORD_RE = re.compile(r"(?i)(fehler\s?codes?|error\s?codes?|\bcodes\b|fehlercodeliste)")
LIST_WORD_RE = re.compile(r"(?i)\b(welche|alle|liste|übersicht|uebersicht|wie\s*viele|which|list|all|how\s*many|gibt\s*es|kennst|gelten)\b")
RANGE_RE = re.compile(
    r"(?i)zwischen\s+E?(\d{3})\s+und\s+E?(\d{3})|between\s+E?(\d{3})\s+and\s+E?(\d{3})|(?<![0-9])E?(\d{3})\s*(?:~|–|bis)\s*E?(\d{3})(?![0-9])"
)
GROUP_RE = re.compile(r"(?i)\b(FJM|CAC|DVM|ERV|EHS)\b")


def _record_lines(rec):
    lines = [
        f"Code: {rec['code']} ({rec['e_code']})",
        f"Original-Fehlermeldung: {rec['message']}",
        f"Produktgruppen: {rec['groups_raw'] or '—'}",
    ]
    if rec.get("note"):
        lines.append(f"Zusatznotiz: {rec['note']}")
    return "\n".join(lines)


def _range_lines(rng):
    lines = [
        f"Fehlercode-Bereich: {rng['key']} (E{rng['from']} bis E{rng['to']})",
        f"Original-Fehlermeldung: {rng['message']}",
        f"Produktgruppen: {rng['groups_raw'] or '—'}",
    ]
    if rng.get("note"):
        lines.append(f"Zusatznotiz: {rng['note']}")
    return "\n".join(lines)


def _neighbor_codes(code, limit=4):
    target = int(code)
    known = sorted(int(c) for c in ERROR_CODES)
    return [str(c) for c in sorted(known, key=lambda c: (abs(c - target), c))[:limit]]


def _covering_range(code):
    value = int(code)
    for rng in ERROR_RANGES:
        if rng["from"] <= value <= rng["to"]:
            return rng
    return None


def detect_error_code_intent(message):
    """Return an intent dict for error-code style questions, or None for normal RAG."""
    if not ERROR_CODES:
        return None
    text = message.strip()

    range_match = RANGE_RE.search(text)
    if range_match:
        nums = [g for g in range_match.groups() if g]
        if len(nums) >= 2:
            lo, hi = sorted((int(nums[0]), int(nums[1])))
            for rng in ERROR_RANGES:
                if rng["from"] == lo and rng["to"] == hi:
                    return {"type": "codes", "records": [], "range_records": [rng], "missing": []}
            if LIST_WORD_RE.search(text) or CODES_WORD_RE.search(text):
                return {"type": "list_range", "from": lo, "to": hi}

    has_context = bool(CODE_CONTEXT_RE.search(text)) or bool(BARE_CODE_RE.match(text))
    candidates = []
    for m in CODE_RE.finditer(text):
        prefixed = m.group(0).lower().startswith("e")
        if prefixed or has_context:
            code = m.group(1)
            if code not in candidates:
                candidates.append(code)
    if candidates:
        records, range_records, missing = [], [], []
        for code in candidates[:3]:
            if code in ERROR_CODES:
                records.append(ERROR_CODES[code])
            else:
                rng = _covering_range(code)
                if rng:
                    range_records.append(rng)
                else:
                    missing.append(code)
        return {"type": "codes", "records": records, "range_records": range_records, "missing": missing}

    if CODES_WORD_RE.search(text) and LIST_WORD_RE.search(text):
        group_match = GROUP_RE.search(text)
        if group_match:
            return {"type": "list_group", "group": group_match.group(1).upper()}
        return {"type": "list_all"}

    return None


def build_dataset_block(intent):
    """Render the verified dataset that gets appended to the user message."""
    parts = []
    instruction = (
        "[ANWEISUNG: Beantworte die obige Nutzerfrage AUSSCHLIESSLICH auf Basis dieser "
        "verifizierten Fehlercode-Daten im Fehlercode-Antwortformat. Diese Daten sind maßgeblich "
        "und aktueller als alle anderen Quellen. Nenne dabei immer die betroffenen Produktgruppen "
        "aus dem Datensatz. Antworte in der Sprache der Nutzerfrage. "
        "Erfinde keine zusätzlichen Ursachen oder Reparaturschritte.]"
    )

    if intent["type"] == "codes":
        for rec in intent["records"]:
            parts.append(_record_lines(rec))
        for rng in intent["range_records"]:
            parts.append(_range_lines(rng))
        for code in intent["missing"]:
            neighbors = ", ".join(_neighbor_codes(code))
            parts.append(
                f"Der Code {code} (E{code}) ist NICHT in der Fehlercode-Datenbank dokumentiert.\n"
                f"Ähnliche dokumentierte Codes: {neighbors}."
            )
        if intent["missing"] and not intent["records"] and not intent["range_records"]:
            instruction = (
                "[ANWEISUNG: Teile ehrlich mit, dass dieser Code nicht in der Wissensdatenbank "
                "dokumentiert ist, biete die ähnlichen Codes als Rückfrage an und erfinde keine "
                "Bedeutung. Antworte in der Sprache der Nutzerfrage.]"
            )

    elif intent["type"] == "list_all":
        by_series = {}
        for code in ERROR_CODES:
            by_series.setdefault(code[0] + "xx", 0)
            by_series[code[0] + "xx"] += 1
        series = " · ".join(f"{k}: {v} Codes" for k, v in sorted(by_series.items()))
        known = sorted(int(c) for c in ERROR_CODES)
        parts.append(
            f"Die Fehlercode-Datenbank enthält {len(ERROR_CODES)} dokumentierte Samsung-Fehlercodes "
            f"(Bereich {known[0]}–{known[-1]}) plus den Sammelbereich 101~120.\n"
            f"Verteilung: {series}.\n"
            "Jeder Code gilt mit und ohne E-Präfix (465 = E465)."
        )
        instruction = (
            "[ANWEISUNG: Nenne die Gesamtzahl und die Verteilung, erkläre, dass einzelne Codes "
            "jederzeit abgefragt werden können, und zähle NICHT alle Codes auf. "
            "Antworte in der Sprache der Nutzerfrage.]"
        )

    elif intent["type"] == "list_range":
        lo, hi = intent["from"], intent["to"]
        hits = [ERROR_CODES[c] for c in sorted(ERROR_CODES, key=int) if lo <= int(c) <= hi]
        if not hits:
            parts.append(f"Im Bereich {lo}–{hi} sind keine Fehlercodes dokumentiert.")
        elif len(hits) <= 40:
            listing = "\n".join(f"- {r['code']} ({r['e_code']}): {r['message']}" for r in hits)
            parts.append(f"Dokumentierte Fehlercodes im Bereich {lo}–{hi} ({len(hits)}):\n{listing}")
        else:
            listing = "\n".join(f"- {r['code']}: {r['message'][:70]}" for r in hits[:20])
            parts.append(
                f"Im Bereich {lo}–{hi} sind {len(hits)} Fehlercodes dokumentiert. Erste 20:\n{listing}"
            )

    elif intent["type"] == "list_group":
        group = intent["group"]
        hits = [r for c, r in sorted(ERROR_CODES.items(), key=lambda kv: int(kv[0])) if group in r["groups"]]
        listing = "\n".join(f"- {r['code']} ({r['e_code']}): {r['message'][:70]}" for r in hits[:25])
        more = f"\n… und {len(hits) - 25} weitere." if len(hits) > 25 else ""
        parts.append(
            f"Für die Produktgruppe {group} sind {len(hits)} Fehlercodes dokumentiert. "
            f"Auswahl:\n{listing}{more}"
        )
        instruction = (
            "[ANWEISUNG: Nenne die Gesamtzahl für die Produktgruppe und eine kompakte Auswahl; "
            "biete an, einzelne Codes im Detail zu erklären. Antworte in der Sprache der Nutzerfrage.]"
        )

    if not parts:
        return None
    block = "\n\n".join(parts)
    return (
        f"\n\n[VERIFIZIERTE FEHLERCODE-DATEN — Quelle: {ERROR_CODES_SOURCE_LABEL}]\n"
        f"{block}\n{instruction}"
    )


def lookup_has_verified_data(intent):
    if intent is None:
        return False
    if intent["type"] == "codes":
        return bool(intent["records"] or intent["range_records"])
    return intent["type"] in {"list_all", "list_range", "list_group"}


# ---------------------------------------------------------------------------
# Rate limiting (per client IP, in-process)
# ---------------------------------------------------------------------------

_RATE_BUCKETS = {}


def client_ip(request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def rate_limited(key, now=None):
    """True when the caller exceeded RATE_LIMIT_PER_MINUTE in the last 60s."""
    if RATE_LIMIT_PER_MINUTE <= 0:
        return False
    now = time.monotonic() if now is None else now
    bucket = _RATE_BUCKETS.setdefault(key, deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return True
    bucket.append(now)
    if len(_RATE_BUCKETS) > 2000:
        for stale in [k for k, v in _RATE_BUCKETS.items() if not v]:
            _RATE_BUCKETS.pop(stale, None)
    return False


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

FEEDBACK_RING = deque(maxlen=200)


# ---------------------------------------------------------------------------
# Agent plumbing
# ---------------------------------------------------------------------------

def _do_headers():
    return {"Authorization": f"Bearer {DO_API_TOKEN}", "Content-Type": "application/json"}


def _normalize_endpoint(url):
    url = url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/api/v1/chat/completions"
    return url


def _configure_agent_from_env():
    """Preferred path: static credentials, no DO API token needed, no key minting."""
    global AGENT_ENDPOINT, AGENT_API_KEY
    endpoint = os.environ.get("AGENT_ENDPOINT", "")
    key = os.environ.get("AGENT_ACCESS_KEY", "")
    if endpoint and key:
        AGENT_ENDPOINT = _normalize_endpoint(endpoint)
        AGENT_API_KEY = key
        logger.info("Using static agent credentials from environment: %s", AGENT_ENDPOINT)
        return True
    return False


def _discover_agent():
    """Legacy fallback: fetch agent details via the DO API and mint an access key.

    Deprecated because it creates a new key on every boot — set AGENT_ENDPOINT +
    AGENT_ACCESS_KEY instead and remove DO_API_TOKEN from the app.
    """
    global AGENT_ENDPOINT, AGENT_API_KEY

    if not AGENT_UUID or not DO_API_TOKEN:
        raise RuntimeError("No agent credentials: set AGENT_ENDPOINT + AGENT_ACCESS_KEY (preferred) or AGENT_UUID + DO_API_TOKEN")

    logger.warning(
        "Legacy discovery path: minting a new agent API key at startup. "
        "Set AGENT_ENDPOINT + AGENT_ACCESS_KEY to stop key sprawl."
    )
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{DO_API_BASE}/v2/gen-ai/agents/{AGENT_UUID}", headers=_do_headers())
        resp.raise_for_status()
        agent = resp.json()["agent"]

        deployment = agent.get("deployment", {})
        deploy_url = deployment.get("url")
        if not deploy_url:
            logger.error("Agent has no deployment URL. Status: %s", deployment.get("status"))
            raise RuntimeError("Agent deployment URL not available")
        AGENT_ENDPOINT = f"{deploy_url}/api/v1/chat/completions"
        logger.info("Agent endpoint: %s", AGENT_ENDPOINT)

        key_resp = client.post(
            f"{DO_API_BASE}/v2/gen-ai/agents/{AGENT_UUID}/api_keys",
            headers=_do_headers(),
            json={"name": "chat-ui"},
        )
        key_resp.raise_for_status()
        AGENT_API_KEY = key_resp.json()["api_key_info"]["secret_key"]
        logger.info("Agent API key created")


def _ensure_agent_ready():
    """Retry legacy discovery at most once per DISCOVERY_RETRY_SECONDS."""
    global DISCOVERY_ERROR, LAST_DISCOVERY_ATTEMPT
    if AGENT_ENDPOINT and AGENT_API_KEY:
        return True
    now = time.monotonic()
    if now - LAST_DISCOVERY_ATTEMPT < DISCOVERY_RETRY_SECONDS:
        return False
    LAST_DISCOVERY_ATTEMPT = now
    try:
        if _configure_agent_from_env():
            DISCOVERY_ERROR = None
            return True
        _discover_agent()
        DISCOVERY_ERROR = None
        return True
    except Exception as exc:
        DISCOVERY_ERROR = str(exc)
        logger.exception("Agent discovery failed")
        return False


@app.on_event("startup")
async def startup_event():
    global DISCOVERY_ERROR, LAST_DISCOVERY_ATTEMPT
    LAST_DISCOVERY_ATTEMPT = time.monotonic()
    try:
        if not _configure_agent_from_env():
            _discover_agent()
        DISCOVERY_ERROR = None
    except Exception as exc:
        DISCOVERY_ERROR = str(exc)
        logger.exception("Agent discovery failed; chat endpoint will retry lazily")


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
        "agent_error": "agent_not_configured" if DISCOVERY_ERROR else None,
        "lookup_codes": len(ERROR_CODES),
        "streaming": STREAMING_ENABLED,
        "provider_degraded": provider_status["degraded"],
        "provider_components": provider_status["components"],
    }


def _sanitize_history(raw_history):
    cleaned = []
    if not isinstance(raw_history, list):
        return cleaned
    for item in raw_history[-MAX_HISTORY_ENTRIES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content[:4000]})
    return cleaned


class _PreparedChat:
    """Everything both the streaming and the non-streaming endpoint need."""

    def __init__(self, messages, lookup_used, intent, request_id, started, debug, provider_status):
        self.messages = messages
        self.lookup_used = lookup_used
        self.intent = intent
        self.request_id = request_id
        self.started = started
        self.debug = debug
        self.provider_status = provider_status

    def elapsed_ms(self):
        return int((time.monotonic() - self.started) * 1000)

    def base_meta(self):
        meta = {
            "request_id": self.request_id,
            "latency_ms": self.elapsed_ms(),
            "provider_degraded": self.provider_status["degraded"],
        }
        if self.provider_status["degraded"]:
            meta["provider_hint"] = PROVIDER_DEGRADED_HINT
            meta["provider_components"] = self.provider_status["components"]
        return meta

    def debug_block(self, **extra):
        if not self.debug:
            return None
        block = {
            "intent": self.intent["type"] if self.intent else None,
            "lookup_used": self.lookup_used,
            "history_turns": len(self.messages) - 1,
            "agent_timeout_s": AGENT_TIMEOUT_SECONDS,
        }
        block.update(extra)
        return block


async def _prepare_chat(request):
    """Validate + build the agent payload. Returns _PreparedChat or JSONResponse error."""
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()

    if rate_limited(client_ip(request)):
        logger.warning("[%s] rate limited", request_id)
        return JSONResponse(
            status_code=429,
            content={"error": RATE_LIMIT_MESSAGE, "retrieval_status": "error", "request_id": request_id},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Ungültige Anfrage.", "request_id": request_id})

    message = body.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return JSONResponse(status_code=400, content={"error": "Bitte geben Sie eine Frage ein.", "request_id": request_id})
    message = message.strip()[:MAX_MESSAGE_CHARS]

    provider_status = await _get_provider_status()

    if not _ensure_agent_ready():
        return JSONResponse(
            content={
                "error": NO_ANSWER_MESSAGE,
                "retrieval_status": "error",
                "request_id": request_id,
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )
    history = _sanitize_history(body.get("history", []))
    debug = bool(body.get("debug"))

    intent = detect_error_code_intent(message) if LOOKUP_ENABLED else None
    dataset_block = build_dataset_block(intent) if intent else None
    lookup_used = dataset_block is not None and lookup_has_verified_data(intent)

    agent_message = message + dataset_block if dataset_block else message
    messages = history + [{"role": "user", "content": agent_message}]

    logger.info(
        "[%s] agent request: history=%d lookup=%s message=%r",
        request_id, len(history), intent["type"] if intent else "-", message[:200],
    )
    return _PreparedChat(messages, lookup_used, intent, request_id, started, debug, provider_status)


def _agent_payload(prepared, stream):
    return {
        "messages": prepared.messages,
        "include_retrieval_info": True,
        "include_guardrails_info": True,
        "stream": stream,
    }


def _agent_headers():
    return {"Authorization": f"Bearer {AGENT_API_KEY}", "Content-Type": "application/json"}


NO_INFO_MARKERS = (
    "keine gesicherten Informationen",
    "keine Angabe dazu finden",
)
# The agent occasionally answers with its own error text (e.g. its rate limit).
# That must never reach the chat window.
UPSTREAM_ERROR_RE = re.compile(r"^\s*(Error code:\s*\d{3}|\{['\"]error['\"])")
UPSTREAM_BUSY_MESSAGE = (
    "Der Wissensassistent ist gerade stark ausgelastet. "
    "Bitte versuchen Sie es in einer Minute noch einmal."
)


def sanitize_upstream_error(content):
    """Return (content, is_error): replace raw agent error payloads with plain German."""
    if content and UPSTREAM_ERROR_RE.match(content):
        logger.warning("upstream error surfaced in content: %s", content[:200])
        return UPSTREAM_BUSY_MESSAGE, True
    return content, False
REFERRAL_SENTENCE = (
    "Eden Klima hilft hier gerne persönlich weiter: "
    "https://www.eden-klima.at/klimaanlagen-wartung/preisrechner/"
)


# The model likes typographic whitespace and hyphens ("Eden Klima",
# "Compressor‑Overload"). Normalize before any substring check.
_TYPO_MAP = {
    " ": " ", " ": " ", " ": " ", " ": " ",
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
}


def normalize_text(value):
    if not value:
        return ""
    for src, dst in _TYPO_MAP.items():
        value = value.replace(src, dst)
    return value


def ensure_referral(content):
    """A 'no information' answer must still point the customer to Eden Klima."""
    if not content:
        return content
    normalized = normalize_text(content)
    if not any(marker in normalized for marker in NO_INFO_MARKERS):
        return content
    lowered = normalized.lower()
    if "eden klima" in lowered or "eden-klima.at" in lowered:
        return content
    return content.rstrip() + "\n\n" + REFERRAL_SENTENCE


def _apply_guardrail_replacement(content, sources, guardrails):
    """Replace the platform's canned English refusal with the German safety answer."""
    if any(marker in content for marker in GUARDRAIL_CANNED_MARKERS):
        if "content_moderation" not in guardrails:
            guardrails.append("content_moderation")
        return GUARDRAIL_SAFE_MESSAGE, [], guardrails
    return content, sources, guardrails


@app.post("/api/chat")
async def chat(request: Request):
    """Proxy a chat message to the managed agent and return the full response."""
    prepared = await _prepare_chat(request)
    if isinstance(prepared, JSONResponse):
        return prepared

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS) as client:
            resp = await client.post(AGENT_ENDPOINT, json=_agent_payload(prepared, False), headers=_agent_headers())
    except httpx.HTTPError as exc:
        logger.warning("[%s] agent request failed: %s", prepared.request_id, exc)
        return JSONResponse(
            content={"content": KB_UNAVAILABLE_MESSAGE, "retrieval_status": "error", **prepared.base_meta()},
        )

    logger.info("[%s] agent response status_code=%s", prepared.request_id, resp.status_code)

    try:
        data = resp.json()
    except Exception:
        return JSONResponse(
            content={"content": KB_UNAVAILABLE_MESSAGE, "retrieval_status": "error", **prepared.base_meta()},
        )

    if resp.status_code >= 500:
        logger.warning("[%s] agent 5xx: %s", prepared.request_id, str(data)[:300])
        return JSONResponse(
            content={"content": KB_UNAVAILABLE_MESSAGE, "retrieval_status": "error", **prepared.base_meta()},
        )

    content = _clean_content(_extract_content(data))
    sources, retrieval_status = _extract_sources(data, prepared.lookup_used)
    if prepared.lookup_used:
        retrieval_status = "lookup"
    guardrails = _extract_guardrails(data)
    content, sources, guardrails = _apply_guardrail_replacement(content, sources, guardrails)
    content, upstream_error = sanitize_upstream_error(content)
    if upstream_error:
        sources, retrieval_status = [], "error"
    else:
        content = ensure_referral(content)

    if not content:
        logger.warning("[%s] agent returned no content. keys=%s", prepared.request_id, sorted(data.keys()))
        content = NO_ANSWER_MESSAGE
        retrieval_status = "error"

    logger.info(
        "[%s] done in %sms status=%s sources=%d",
        prepared.request_id, prepared.elapsed_ms(), retrieval_status, len(sources),
    )

    payload = {
        "content": content,
        "usage": data.get("usage"),
        "sources": sources,
        "retrieval_status": retrieval_status,
        "guardrails": guardrails,
        **prepared.base_meta(),
    }
    debug_block = prepared.debug_block(usage=data.get("usage"), streamed=False)
    if debug_block:
        payload["debug"] = debug_block
    return JSONResponse(content=payload)


# --- streaming ---------------------------------------------------------------

# A citation marker can straddle two SSE chunks, so hold back a tail that could
# still grow into one ("[", "[[C1", …) instead of emitting it to the browser.
# Trailing whitespace is held back too: it may belong to a marker that is about
# to be removed, and emitting it early would leave a double space behind.
PARTIAL_MARKER_RE = re.compile(r"(?:\s+|\s*\[[\[\sC0-9\]]*)$")


def split_streamable(buffer):
    """Split accumulated text into (emit_now, keep_for_next_chunk)."""
    cleaned = CITATION_MARKER_RE.sub("", buffer)
    match = PARTIAL_MARKER_RE.search(cleaned)
    if match:
        return cleaned[: match.start()], cleaned[match.start():]
    return cleaned, ""


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_stream_chunk(raw):
    """Return (delta_text, payload_dict) for one SSE data line of the agent."""
    if not raw or raw == "[DONE]":
        return "", None
    try:
        payload = json.loads(raw)
    except Exception:
        return "", None
    delta = ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        piece = first.get("delta") if isinstance(first, dict) else None
        if isinstance(piece, dict) and isinstance(piece.get("content"), str):
            delta = piece["content"]
        elif isinstance(first, dict) and isinstance(first.get("text"), str):
            delta = first["text"]
    return delta, payload


@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """Stream the agent answer as server-sent events."""
    if not STREAMING_ENABLED:
        return JSONResponse(status_code=501, content={"error": "streaming disabled"})

    prepared = await _prepare_chat(request)
    if isinstance(prepared, JSONResponse):
        return prepared

    async def event_stream():
        yield _sse("start", {"request_id": prepared.request_id})
        buffer = ""
        emitted = ""
        collected = {}
        failed = False
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST", AGENT_ENDPOINT, json=_agent_payload(prepared, True), headers=_agent_headers()
                ) as resp:
                    if resp.status_code >= 400:
                        await resp.aread()
                        logger.warning("[%s] stream http %s", prepared.request_id, resp.status_code)
                        failed = True
                    else:
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            delta, payload = _parse_stream_chunk(line[5:].strip())
                            if payload:
                                for key in ("retrieval", "guardrails", "usage"):
                                    if payload.get(key):
                                        collected[key] = payload[key]
                            if not delta:
                                continue
                            buffer += delta
                            emit, buffer = split_streamable(buffer)
                            if emit:
                                emitted += emit
                                yield _sse("delta", {"text": emit})
        except httpx.HTTPError as exc:
            logger.warning("[%s] stream failed: %s", prepared.request_id, exc)
            failed = True

        if buffer:
            tail = CITATION_MARKER_RE.sub("", buffer)
            if tail:
                emitted += tail
                yield _sse("delta", {"text": tail})

        content = emitted.strip()
        sources, retrieval_status = _extract_sources(collected, prepared.lookup_used)
        if prepared.lookup_used:
            retrieval_status = "lookup"
        guardrails = _extract_guardrails(collected)
        content, sources, guardrails = _apply_guardrail_replacement(content, sources, guardrails)
        content, upstream_error = sanitize_upstream_error(content)
        if upstream_error:
            sources, retrieval_status = [], "error"
        else:
            content = ensure_referral(content)

        replaced = content != emitted.strip()
        if failed or not content:
            content = KB_UNAVAILABLE_MESSAGE if failed else NO_ANSWER_MESSAGE
            retrieval_status = "error"
            sources = []
            replaced = True

        meta = {
            "content": content,
            "sources": sources,
            "retrieval_status": retrieval_status,
            "guardrails": guardrails,
            "replace_content": replaced,
            **prepared.base_meta(),
        }
        debug_block = prepared.debug_block(usage=collected.get("usage"), streamed=True)
        if debug_block:
            meta["debug"] = debug_block

        logger.info(
            "[%s] stream done in %sms status=%s sources=%d chars=%d",
            prepared.request_id, prepared.elapsed_ms(), retrieval_status, len(sources), len(content),
        )
        yield _sse("meta", meta)
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --- feedback ----------------------------------------------------------------

@app.post("/api/feedback")
async def feedback(request: Request):
    """Store a thumbs up/down for an answer (structured log + in-memory ring)."""
    if rate_limited("fb:" + client_ip(request)):
        return JSONResponse(status_code=429, content={"error": RATE_LIMIT_MESSAGE})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Ungültige Anfrage."})

    verdict = body.get("verdict")
    if verdict not in ("yes", "no"):
        return JSONResponse(status_code=400, content={"error": "verdict muss 'yes' oder 'no' sein."})

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "request_id": str(body.get("request_id", ""))[:32],
        "session_id": str(body.get("session_id", ""))[:64],
        "question": str(body.get("question", ""))[:200],
    }
    FEEDBACK_RING.append(entry)
    logger.info("FEEDBACK %s", json.dumps(entry, ensure_ascii=False))
    return JSONResponse(content={"status": "ok"})


@app.get("/api/feedback/summary")
async def feedback_summary():
    """Recent feedback held in memory. Durable record is the FEEDBACK log line."""
    yes = sum(1 for e in FEEDBACK_RING if e["verdict"] == "yes")
    return {
        "window": FEEDBACK_RING.maxlen,
        "count": len(FEEDBACK_RING),
        "yes": yes,
        "no": len(FEEDBACK_RING) - yes,
        "recent": list(FEEDBACK_RING)[-20:],
    }


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


CITATION_MARKER_RE = re.compile(r"\s*\[+\s*C\d+\s*\]+")


def _clean_content(text):
    """Strip inline [[C1]]/[C2] citation markers — sources are shown separately."""
    return CITATION_MARKER_RE.sub("", text or "").strip()


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


def _extract_sources(data, lookup_used=False):
    """Read retrieval.retrieved_data (the documented location) into UI-friendly sources.

    Returns (sources, retrieval_status) where status is success/empty/unknown.
    """
    sources = []
    if lookup_used:
        sources.append({"filename": ERROR_CODES_SOURCE_LABEL, "page": None, "score": None})

    retrieved = None
    if isinstance(data, dict):
        retrieval = data.get("retrieval")
        if isinstance(retrieval, dict):
            retrieved = retrieval.get("retrieved_data")

    if not isinstance(retrieved, list):
        return sources, "unknown"

    status = "success" if retrieved else "empty"
    seen = set()
    for item in retrieved:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename") or item.get("item_name") or ""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        page = item.get("page_number") or metadata.get("page_number") or metadata.get("page")
        if not filename:
            continue
        key = (filename, page)
        if key in seen:
            continue
        seen.add(key)
        score = item.get("score")
        if not isinstance(score, (int, float)) or not (0 <= score <= 1):
            score = None  # platform sentinel values (e.g. -9549511700) are not real scores
        sources.append({"filename": filename, "page": page, "score": score})
        if len(sources) >= 6:
            break
    return sources, status


def _extract_guardrails(data):
    if not isinstance(data, dict):
        return []
    guardrails = data.get("guardrails")
    if not isinstance(guardrails, dict):
        return []
    triggered = guardrails.get("triggered_guardrails")
    if not isinstance(triggered, list):
        return []
    return [g.get("rule_name") for g in triggered if isinstance(g, dict) and g.get("rule_name")]
