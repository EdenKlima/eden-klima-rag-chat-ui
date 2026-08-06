# 03 — Code-Audit (Repo EdenKlima/eden-klima-rag-chat-ui @ 8bc0533)

Struktur: `main.py` (FastAPI-Proxy, 301 Zeilen) · `static/index.html` (UI, 913 Zeilen) · `Dockerfile` · `requirements.txt` (fastapi 0.115, uvicorn 0.30, httpx 0.27) · **Duplikat** `blueprints/rag-assistant/chat-ui/` (identisch bis auf README — laut README für die App-Platform-Quellkonfiguration; App-Spec nennt jedoch `source_dir: /` → klären, welcher Pfad wirklich deployt; Duplikat ist Wartungsrisiko).

## Befunde Backend (main.py)

| # | Schwere | Befund | Beleg |
|---|---|---|---|
| B1 | **KRITISCH** | `_discover_agent()` erzeugt bei jedem Start per `POST /v2/gen-ai/agents/{id}/api_keys` einen **neuen** Access-Key, löscht nie alte → ≥2 Seiten „chat-ui"-Keys in der Konsole. | Z. 88–96 |
| B2 | **KRITISCH** | App hält den **account-weiten `DO_API_TOKEN`** zur Laufzeit, nur um Endpoint zu entdecken + Keys zu minten. Öffentliche Angriffsfläche ↔ Vollzugriff aufs DO-Konto. Richtig: 1 statischer Agent-Key als Env-Secret, kein DO-Token in der App. | Z. 30, 57–58 |
| B3 | HOCH | `_extract_sources()` prüft `sources`/`citations`/`retrieval_info`/`retrievalInfo` — die API liefert aber `retrieval.retrieved_data[]` (mit `filename`, `page`, `score`). → Quellen fast nie extrahiert; `citations`-Objekte (ohne `filename`) verwirft die UI. | Z. 273–288 |
| B4 | HOCH | Startup-Discovery ohne Retry: schlägt der eine DO-API-Call beim Boot fehl, bleibt die App dauerhaft „not ready" bis zum nächsten Deploy (beobachtetes „Keine Antwort erhalten" nach Redeploys). Kein Lazy-Retry im Request-Pfad. | Z. 99–107, 142–147 |
| B5 | MITTEL | KB-Timeout ≠ „nicht gefunden" wird nirgends unterschieden: `retrieval`-/`guardrails`-Info wird angefordert, aber ignoriert; das Modell bekommt bei Retrieval-Ausfall leeren Kontext und sagt fälschlich „keine gesicherten Informationen". `retrieval_status` fehlt im API-Vertrag. | Z. 172–201 |
| B6 | MITTEL | Fehlerantworten kommen mit **HTTP 200** + `{"error": …}` (kein `status_code`) — Frontend kompensiert, Vertrag bleibt inkonsistent. | Z. 142–147 |
| B7 | MITTEL | History ungekappt: Client sendet die komplette Konversation, Server reicht alles durch → Requests wachsen unbegrenzt; Client kann beliebige Rollen (auch `system`) injizieren. | Z. 149–158 |
| B8 | MITTEL | Statuspage-Gate: jede Chat-Anfrage wird gegen status.digitalocean.com-Komponenten geprüft (60-s-Cache); Substring-Matching (`"Inference"` etc.) kann bei unspezifischen Incidents die App global lahmlegen. Als Schutz gedacht, als globaler Kill-Switch riskant. | Z. 204–237 |
| B9 | NIEDRIG | `include_guardrails_info` angefordert, nie ausgewertet (Guardrail-Block nicht von Leerantwort unterscheidbar). | Z. 176 |
| B10 | NIEDRIG | Kein Rate-Limit/Auth auf `/api/chat`; `message` ohne Längenlimit. | Z. 128 ff. |
| B11 | NIEDRIG | `@app.on_event("startup")` deprecated (Lifespan-API); kein `.dockerignore` → `.git/`, `blueprints/` im Image. | Dockerfile Z. 8 |
| B12 | INFO | Kein Streaming (`stream: false`) — Antworten erscheinen erst komplett (bis 14 s gemessen). | Z. 176 |
| B13 | INFO | Logging maßvoll, keine Secrets geloggt ✓; `/health` gibt `agent_error`-Interna preis (klein). | Z. 116–125 |

## Befunde Frontend (static/index.html)

| # | Schwere | Befund |
|---|---|---|
| F1 | ✓ OK | Doppel-Submit-Schutz (`loading`-Flag, Button+Textarea disabled), Enter/Shift-Enter korrekt, genau 1 Request pro Nachricht. |
| F2 | ✓ OK | XSS: `escapeHtml()` vor jeder Formatierung, dann erst `innerHTML` — sauber. Tabellen-Rendering mit Divider-Erkennung + Scroll-Wrapper vorhanden. |
| F3 | HOCH | `normalizeSources()` akzeptiert nur Objekte mit `title/name/file_name/filename/url` — die realen `citations`-Chunks haben keins davon → Quellenliste bleibt leer, obwohl die Antwort `[[C1]]`-Marker enthält. Marker werden zudem nicht in Fußnoten/Links umgewandelt. |
| F4 | MITTEL | Feedback-Buttons („Ja/Nein") sind rein clientseitig — **nichts wird gespeichert oder gesendet**; kein Endpoint, keine Session-ID, kein Verlaufspersistieren (Reload = alles weg). |
| F5 | MITTEL | Markdown-Renderer kann keine `#`-Überschriften und keine `[Links](…)` — Agent ist aber angewiesen, Überschriften zu nutzen → rohe `**…**`-Struktur wird zwar gerendert, `###` erschiene als Text. |
| F6 | NIEDRIG | Kein Client-Timeout/AbortController (hängt am 90-s-Server-Timeout); Fehlertexte ok. |
| F7 | NIEDRIG | Logos direkt von eden-klima.at (Fremd-Origin im Piloten ok). |
| F8 | INFO | Kein Debug-Modus, keine Latenz-/Request-ID-Anzeige. |

## Git-Historie (15 Commits, 30.06.–02.07.)

Saubere, kleine Schritte; erkennbar reaktives Bugfixing während des DO-Incidents (Maintenance-Gate 8cf0896, leere Antworten 14dec0e, Parsing de7e13b, Tabellen 8bc0533). Keine Regression durch den Repo-Wechsel erkennbar; Arbeitskopie clean, Root und `blueprints/`-Kopie synchron.

## Empfohlener API-Vertrag (Soll, aus dem Prompt übernommen)

```json
{
  "content": "…",
  "sources": [{"filename": "…", "page": 19, "score": 0.91}],
  "retrieval_status": "success|empty|timeout|error",
  "guardrails": [],
  "request_id": "…",
  "latency_ms": 1234
}
```
