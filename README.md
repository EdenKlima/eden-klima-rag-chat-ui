# Eden Klima RAG Chat UI

FastAPI chat UI for the **Eden Klima Wissensassistent**. The app serves a static German frontend and proxies chat requests to a DigitalOcean managed GenAI agent with a knowledge base.

Error-code questions do **not** rely on vector search: a regex detects the code, the verified record is loaded from `data/error_codes.json` and injected into the agent request (deterministic lookup path). Everything else (manuals, remote control, maintenance) uses normal knowledge-base retrieval.

## Features

- Eden Klima branded German interface with HVAC prompt examples and safety note
- **Deterministic error-code lookup** (446 Samsung codes, with/without `E` prefix, typo-tolerant, list/range/product-group questions answered from data, not retrieval)
- Source display from `retrieval.retrieved_data` (filename + page), deduplicated; inline `[[C1]]` markers stripped
- `retrieval_status` in every response (`lookup` / `success` / `empty` / `error`) — KB outages render as a warning, not as "no information"
- Duplicate-submit protection, history capped at 16 turns, role whitelist, message length limit
- Clean fallback messages, feedback CTA flow, Markdown rendering incl. tables

## Environment Variables

Preferred (no DigitalOcean API token in the app, no key minting):

```bash
AGENT_ENDPOINT="https://<agent-subdomain>.agents.do-ai.run"   # base URL or full .../api/v1/chat/completions
AGENT_ACCESS_KEY="<one dedicated agent access key>"
```

Legacy fallback (deprecated — creates a new agent key on every boot):

```bash
AGENT_UUID="your-digitalocean-agent-uuid"
DO_API_TOKEN="your-digitalocean-api-token"
```

Optional: `AGENT_NAME`, `LOOKUP_ENABLED=0`, `MAX_MESSAGE_CHARS`, `MAX_HISTORY_ENTRIES`, `DO_API_BASE`, `DO_STATUS_URL`.

Do not commit real token values to the repository.

## Data Pipeline

Single source of truth: `data/samsung_error_codes_master.md`. Regenerate the derived files after editing it:

```bash
python3 scripts/generate_error_data.py
```

Outputs (both committed):

- `data/samsung_air_conditioner_error_codes.md` — lean per-code sections (`## 465 (E465) — …`) for the knowledge base upload
- `data/error_codes.json` — lookup database used by `main.py`

## Run Locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AGENT_ENDPOINT="..." AGENT_ACCESS_KEY="..."
uvicorn main:app --host 0.0.0.0 --port 8080
```

## Tests & Evaluation

```bash
python3 scripts/test_lookup.py     # offline tests for the lookup path (no network)

python3 scripts/eval.py \
  --base-url https://rag-assistant-hh9v-chat-wlm7q.ondigitalocean.app \
  --out docs/audit/results/eval-$(date +%F).csv
```

Run the eval before and after every deploy. Cases with `expect_status: "lookup"` must be 100% green; safety cases (36–40) are deploy blockers.

## Deploy on DigitalOcean App Platform

The included `Dockerfile` runs the app with Uvicorn on port `8080`. Pushing to `main` triggers the App Platform deployment.

This repository keeps the app in two locations:

- repository root, for local development
- `blueprints/rag-assistant/chat-ui`, for the existing DigitalOcean App Platform source configuration

**When changing app code, keep the root files and the `blueprints/rag-assistant/chat-ui` copy in sync** (`main.py`, `static/`, `data/`, `Dockerfile`, `requirements.txt`, `.dockerignore`).

## Agent Request

```json
{
  "messages": [],
  "include_retrieval_info": true,
  "include_guardrails_info": true,
  "stream": false
}
```

The backend reads `retrieval.retrieved_data` for sources, `guardrails.triggered_guardrails` for guardrail info, and logs diagnostics server-side only (never tokens).

## Audit

A full read-only audit (architecture, retrieval benchmark, costs, security) plus the implementation plan lives in `docs/audit/`.
