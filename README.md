# Eden Klima RAG Chat UI

FastAPI chat UI for the Eden Klima Wissensassistent. The app serves a static German frontend and proxies chat requests to a DigitalOcean managed GenAI agent with a knowledge base.

## Features

- Eden Klima branded German interface
- HVAC-focused prompt examples for Klimaanlagen, Wärmepumpen, Wartung and Kälte- und Klimatechnik
- Safety note for work involving electricity, refrigerant and safety-relevant components
- Placeholder CTA links below assistant answers
- Optional source/citation display when retrieval metadata is returned by the backend
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

In App Platform, configure:

- Build source: this repository
- Runtime: Dockerfile
- HTTP port: `8080`
- Environment variables: `AGENT_UUID`, `DO_API_TOKEN`, and optionally `AGENT_NAME`

## Project Structure

```text
.
├── Dockerfile
├── main.py
├── requirements.txt
└── static
    └── index.html
```

## Notes

The backend discovers the DigitalOcean GenAI agent endpoint and creates an agent API key at startup. The authentication flow is inherited from the DigitalOcean RAG Assistant blueprint and should not need changes for normal UI customization.
