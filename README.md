# Eden Klima RAG Chat UI

FastAPI chat UI for the **Eden Klima Wissensassistent**. The app serves a static German frontend and proxies chat requests to a DigitalOcean managed GenAI agent with a knowledge base.

## Features

- Eden Klima branded German interface
- HVAC-focused prompt examples for Klimaanlagen, Wärmepumpen, Wartung and Kälte- und Klimatechnik
- Safety note for work involving electricity, refrigerant and safety-relevant components
- Basic Markdown rendering for assistant answers
- Clean fallback messages for users when the agent cannot generate an answer
- Feedback CTA flow after answers:
  - `Ja` shows a friendly confirmation
  - `Nein` shows a next-step suggestion and links to the Eden Klima price calculator
- Optional source/citation display when retrieval metadata is returned by the backend, with empty/raw JSON citations hidden
- Duplicate-submit protection while an answer is loading
- Small FastAPI app that is deployable on DigitalOcean App Platform

## Requirements

- Python 3.12
- DigitalOcean managed GenAI agent
- DigitalOcean API token with access to the agent

## Environment Variables

The app expects these variables at runtime:

```bash
AGENT_UUID=your-digitalocean-agent-uuid
DO_API_TOKEN=your-digitalocean-api-token
```

Optional:

```bash
AGENT_NAME="Eden Klima Wissensassistent"
DO_API_BASE="https://api.digitalocean.com"
```

Do not commit real token values to the repository.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export AGENT_UUID="your-digitalocean-agent-uuid"
export DO_API_TOKEN="your-digitalocean-api-token"

uvicorn main:app --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

## Deploy on DigitalOcean App Platform

The included `Dockerfile` runs the app with Uvicorn on port `8080`.

This repository keeps the app in two locations:

- repository root, for local development
- `blueprints/rag-assistant/chat-ui`, for the existing DigitalOcean App Platform source configuration

In App Platform, configure:

- Build source: this repository
- Source directory: `blueprints/rag-assistant/chat-ui`
- Runtime: Dockerfile
- HTTP port: `8080`
- Environment variables: `AGENT_UUID`, `DO_API_TOKEN`, and optionally `AGENT_NAME`

## Project Structure

```text
.
├── Dockerfile
├── main.py
├── requirements.txt
├── static
│   └── index.html
└── blueprints
    └── rag-assistant
        └── chat-ui
            ├── Dockerfile
            ├── main.py
            ├── requirements.txt
            └── static
                └── index.html
```

When changing app code, keep the root files and `blueprints/rag-assistant/chat-ui` copy in sync.

## Agent Request

The backend sends chat requests to the DigitalOcean agent using:

```json
{
  "messages": [],
  "include_retrieval_info": true,
  "include_guardrails_info": true,
  "stream": false
}
```

The backend logs agent request/response diagnostics server-side only. These details are not shown to users in the chat UI.

## RAG Notes

If the assistant gives fallback answers such as “Die Antwort konnte gerade nicht generiert werden” or says that no secured information is available, check the DigitalOcean Agent Platform logs and knowledge base:

- Confirm the relevant documents are uploaded and indexed.
- Prefer RAG-friendly Markdown for exact error-code lookup.
- Check for retrieval timeouts.
- Check guardrail blocks or false positives.
- Short queries like `103` or `E554` may need clean indexed sections in the knowledge base.

## Notes

The backend discovers the DigitalOcean GenAI agent endpoint and creates an agent API key at startup. The authentication flow is inherited from the DigitalOcean RAG Assistant blueprint and should not need changes for normal UI customization.
