# Executive Summary — Audit Eden Klima Wissensassistent (2026-08-06)

Read-only-Audit. Keine Änderungen an DigitalOcean, GitHub, Knowledge Base oder produktiven Ressourcen vorgenommen. Alle Belege in `docs/audit/results/`.

## Wichtigste Ursache (Root Cause)

**Die Knowledge Base enthält die falsche Version der Fehlercode-Datei.**
Indexiert ist eine 40,21-KiB-**Tabellenversion** (Original-Tabelle, alle ~446 Codes als kompakte `TableChunk`s, hochgeladen 30.06. 19:52, 10.340 Tokens). Die lokal erstellte, RAG-optimierte **372,5-KiB-Abschnittsversion** (447 `##`-Sektionen mit Customer-safe summary etc., zuletzt geändert 30.06. 21:02 — *nach* dem letzten Upload) **wurde nie hochgeladen**.

Auf diesen zahlenlastigen Tabellen-Chunks bricht das Standard-Retrieval (Hybrid, Alpha ≈ 0.5, K = 5) systematisch ein:

| Query (KB-Retrieve-Playground, live gemessen) | Alpha | Ergebnis |
|---|---|---|
| `Compressor overload error` | 0 (BM25) | ✅ md-TableChunk (464+465) Rang 1 |
| `error 465` | 0.5 | ✅ md-TableChunk Rang 1 |
| `E465` | 0 | ❌ 0 md-Treffer (Datei schreibt nie „E465", nur „465" → BM25 kann nicht matchen) |
| `Was bedeutet Fehler 465?` | 0.5 | ❌ alle 5 Treffer = deutsches Handbuch-PDF, md unsichtbar |

Deutsche Formulierungen (der Normalfall!) und E-Präfix-Schreibweisen verfehlen die Tabellen-Chunks also **strukturell**; dazu kommen **transiente Fenster** (bestätigter DO-Incident „Agent Timeouts While Retrieving Data from Knowledge Bases", 1.–2. Juli — exakt der Test-Zeitraum; identische Query „error 465" schlug 09:33 via App fehl und lief 09:57 via Konsole korrekt). „Welche Fehlercodes kennst du?" ist mit K=5-RAG **prinzipiell** nicht beantwortbar (446 Codes ≫ 5 Chunks).

## Wichtigste Qualitätsprobleme

1. Falsche/veraltete Datei in der KB (s.o.) — Codes werden „ehrlich" verweigert oder aus dem PDF-Handbuch (teils widersprüchlich, z. B. 422) beantwortet.
2. Fehlercodes sind strukturierte Schlüssel — reines semantisches RAG ist das falsche Werkzeug; es fehlt ein deterministischer Lookup.
3. Quellenanzeige defekt: Backend liest `retrieval_info`, die API liefert `retrieval.retrieved_data`; Citation-Objekte ohne `filename` werden von der UI verworfen → Nutzer sehen `[[C1]]`-Marker ohne Quellenliste.
4. Kein Reranker konfiguriert; Embedding Qwen3 0.6B auf 447 nahezu identischen Boilerplate-Sektionen (die geplante neue Datei!) wird Codes ebenfalls kaum unterscheiden — die Datei muss **vor** dem Upload entschlackt werden.
5. Agent-Instructions verlangen „prüfe E-Schreibweise und reine Zahl" — das LLM steuert das Retrieval aber nicht; die Regel ist wirkungslos.

## Wichtigste Sicherheitsprobleme

1. **KRITISCH:** Die öffentliche Chat-App hält den **account-weiten `DO_API_TOKEN`** und erzeugt bei **jedem App-Start einen neuen Agent-Access-Key** („chat-ui", 2 Seiten Keys seit 30.06., nie gelöscht). Kompromittierung der App = Kompromittierung des gesamten DO-Accounts.
2. `/api/chat` ist unauthentifiziert und ohne Rate-Limit (Token-Burn/Abuse möglich; aktuell durch günstige Modelle begrenzt).
3. Client kann beliebige `role`-Werte in die History injizieren (auch `system`).
4. Kein `.dockerignore` (`COPY . .` nimmt `.git/` ins Image).

## Wichtigste Kostenprobleme

$44,60 von $44,68 sind Fixkosten; Tokens sind irrelevant ($0,08):

- App Platform `apps-s-1vcpu-2gb` **$25** — massiv überdimensioniert für einen FastAPI-Proxy (~100 MB RAM). → `apps-s-1vcpu-0.5gb` **$5**.
- OpenSearch `genai-walrus` **$19,60** — Achtung: 40 GiB sind das **Plan-Minimum** des Basic-2GB-Tiers; die vermutete „40-GiB-Storage-Einsparung" existiert **nicht**. Sparhebel ist der **Wechsel auf DigitalOceans serverless Knowledge-Base-Storage** (kbaas; Abrechnung nach Embedding-Tokens, kein eigener Cluster) → Cluster komplett löschen.
- Bonus-Befund: App in FRA, Agent+KB+Cluster in **Toronto (TOR1)** — unnötige Transatlantik-Latenz pro Anfrage.

| Variante | $/Monat (vor USt) |
|---|---|
| A Ist | 44,68 |
| B optimierter DO-Pilot (App 0.5 GB) | ~24,70 |
| C Low-Cost (App 0.5 GB + serverless KB, Cluster gelöscht) | **~5,15** |

## Quick Wins (geordnet nach Wirkung/Aufwand)

1. Korrigierte Fehlercode-Datei hochladen + reindexieren (~$0,004 Indexkosten) — **behebt den Großteil sofort**.
2. Deterministischer Fehlercode-Lookup im FastAPI-Backend (Regex → JSON-Lookup aus der md → LLM formuliert nur noch), RAG nur noch als Fallback mit `alpha 0` + `item_name`-Filter.
3. `_extract_sources` auf `retrieval.retrieved_data[].filename` umstellen; Dateiname+Seite in der UI zeigen.
4. Agent-Key-Hygiene: einen Key erzeugen, als Env-Secret setzen, Minting-Code entfernen, alte Keys löschen, `DO_API_TOKEN` aus der App entfernen.
5. App auf $5-Instanz; Feedback-Buttons persistieren; Eval-/Regressionstests (Testplan liegt bei).

## Empfohlene Zielarchitektur

Zweistufig: (1) Regex erkennt Fehlercode → exakter Lookup in versionierter JSON (aus der md generiert) → LLM übersetzt/formatiert mit eingebettetem Datensatz; (2) alle anderen Fragen → RAG (Hybrid α≈0.5, K=5, Reranker optional) über die PDFs + neue Abschnitts-md. Details: `10-recommended-architecture.md`.

## Aufwand & Kosten danach

- Quick Wins (1–5): ~1–2 Arbeitstage. Zielkosten Variante B sofort (~$25/Monat), Variante C nach KB-Migration (~$5–6/Monat inkl. USt).
- Vollausbau (Lookup-Layer, Eval-Harness, Streaming, Feedback-Persistenz): +2–3 Tage.

**Alle Änderungen erst nach Freigabe** — siehe Maßnahmenliste mit Risikoklassen in `11-implementation-plan.md`.
