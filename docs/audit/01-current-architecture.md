# 01 — Ist-Architektur (Stand 2026-08-06, read-only erhoben)

## Datenfluss

```
Nutzer (Browser)
  → Eden-Klima-Chat-UI  (App Platform FRA, apps-s-1vcpu-2gb, $25/mo)
      FastAPI-Proxy main.py  /api/chat
      • entdeckt Agent-Endpoint via DO-API beim Start (hält DO_API_TOKEN!)
      • erzeugt bei JEDEM Start einen neuen Agent-Access-Key
  → GenAI Agent rag-assistant-hh9v-agent  (TOR1, GPT-oss-20b)
      Temperatur 0.2 · Top-P 0.8 · Max Tokens 1536 · K=5 · Retrieval Method: None · Citations: on
      Guardrails: Content Moderation ON, Jailbreak ON, Sensitive Data OFF
  → Knowledge Base rag-assistant-hh9v-kb  (kbaas, Embedding Qwen3 0.6B, kein Reranker)
  → OpenSearch genai-walrus  (TOR1! Basic 2GB/1vCPU, 40 GiB = Plan-Minimum, $19.60/mo)
  ← Antwort + citations (+ retrieval.retrieved_data, vom Backend derzeit nicht ausgewertet)
```

## Regionen-Mismatch

| Komponente | Region |
|---|---|
| App Platform (chat-ui) | **FRA** |
| Agent | **TOR1** |
| Knowledge Base / kbaas | TOR1 |
| OpenSearch genai-walrus | TOR1 |

Jeder Chat quert einmal den Atlantik (App→Agent). Agent↔KB↔OpenSearch sind lokal in TOR1. Für einen Wien-Piloten wäre FRA durchgängig richtig; Agent-/KB-Region ist nachträglich nicht umstellbar → Neuanlage nötig (siehe Plan).

## Kennungen

- Team `EdenKlima Team` (`do:team:3cebbff5-…4026`), Projekt `eden-klima-knowledge-assistant` (`8e17dd74-…`)
- Agent-UUID `44bcacc0-749c-11f1-aee4-4e013e2ddde4`, Endpoint `https://iuahhjpgd4wy64ndnf7hormx.agents.do-ai.run`, Visibility Private
- KB-UUID `479333ec-749c-11f1-aee4-4e013e2ddde4`, Retrieve `https://kbaas.do-ai.run/v1/<kb>/retrieve`
- Öffentliche UI `https://rag-assistant-hh9v-chat-wlm7q.ondigitalocean.app/`
- Repo `EdenKlima/eden-klima-rag-chat-ui` (lokal: `/Users/michael/edenklima`), App-Quelle: `main`-Branch, Dockerfile, Port 8080

## Request-/Response-Verhalten (gemessen)

- App→Agent-Payload: `messages` (komplette History + neue Nachricht), `include_retrieval_info: true`, `include_guardrails_info: true`, `stream: false`; httpx-Timeout 90 s; kein Streaming, kein Retry (gut), keine Request-Größenbegrenzung.
- Prompt-Größe pro Anfrage: ~6.700–7.000 Input-Tokens (Instructions + K=5-Chunks, PDFs hierarchisch → Parent-Chunks inkludiert).
- Latenz E2E (14 Live-Tests): 3,9–14,2 s, Median ~5 s.
- Agent-Antwortformat: OpenAI-kompatibel `choices[0].message.content` + `citations`-Feld (Chunk-Objekte mit `id`, `index`=KB-UUID, `page_content`; **ohne** `filename`) + `retrieval.retrieved_data[]` (mit `filename`, `score`, `page`) — Letzteres wird vom Backend nicht gelesen.

## Bekannte Plattform-Störung im Testzeitraum

DigitalOcean-Incident „Agent Timeouts While Retrieving Data from Knowledge Bases": Untersuchung ab 1. Juli 08:39 UTC, identifiziert 2. Juli 03:38 UTC, danach resolved — deckt sich exakt mit den frustrierenden Test-Sessions (UI-Commits enden 2. Juli). Fehlertext damals: `Failed to retrieve data from Knowledge base(s) - timeout`. Solche Fenster erklären einen Teil der beobachteten Inkonsistenz, **nicht** die strukturellen Misses (siehe `06-retrieval-benchmark.md`).
