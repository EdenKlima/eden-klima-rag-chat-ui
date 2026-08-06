# 11 — Umsetzungs- und Migrationsplan (WARTET AUF FREIGABE — bis dahin keine Änderung)

Jede Maßnahme einzeln freigebbar. Risiko: 🟢 risikolos · 🟡 niedrig · 🟠 mittel · 🔴 hoch.

## Phase 0 — Sofortmaßnahmen (Stunden)

| ID | Maßnahme | Risiko | Nutzen | Aufwand | Kosten | Rollback |
|---|---|---|---|---|---|---|
| P0-1 | **Korrigierte Fehlercode-md hochladen** (vorher Datei nach `05` entschlacken: E-Schreibweise in Titel, Boilerplate raus) + alte Tabellen-Datenquelle ersetzen, Reindex | 🟡 (Index ändert sich; Reindex ~$0.004) | behebt Hauptursache | 1–2 h | ~0 | alte Datei re-uploaden (liegt als Kopie vor) |
| P0-2 | **Quellen-Fix Backend+UI**: `retrieval.retrieved_data[].filename/page` extrahieren, `[[C1]]`-Marker verlinken/strippen | 🟢 | Quellen endlich sichtbar; T01-artige Fehlzitate erkennbar | 2–3 h | 0 | git revert |
| P0-3 | **Key-Hygiene**: 1 Agent-Key manuell erzeugen → `AGENT_ENDPOINT`/`AGENT_ACCESS_KEY` als App-Secrets → Discovery-/Minting-Code entfernen → alle alten „chat-ui"-Keys löschen → `DO_API_TOKEN` aus App entfernen + **rotieren** | 🟡 (kurzer Deploy; falscher Key = Chat down) | schließt kritischstes Sicherheitsloch | 2 h | 0 | alten Code re-deployen (Token nötig) |
| P0-4 | `.dockerignore` + Rollen-Whitelist + `message`-Längenlimit + History-Kappung (N=8) | 🟢 | Hygiene | 1 h | 0 | git revert |

## Phase 1 — Deterministischer Fehlercode-Pfad (1–2 Tage)

| ID | Maßnahme | Risiko | Nutzen | Aufwand | Kosten | Rollback |
|---|---|---|---|---|---|---|
| P1-1 | md → `error_codes.json`-Generator (Build-Step) + Regex-Erkennung + Lookup-Pfad inkl. Listen-/Bereichs-/Produktgruppen-Intents; LLM formatiert mit eingebettetem Datensatz | 🟡 | Codes 100 % deterministisch | 1 Tag | 0 | Feature-Flag `LOOKUP_ENABLED=0` |
| P1-2 | `retrieval_status` im API-Vertrag + UI-Unterscheidung Timeout vs. leer; Guardrail-Info auswerten | 🟢 | ehrliche Fehlerbilder | 2–3 h | 0 | git revert |
| P1-3 | Eval-Runner aus `12-test-plan.md` (50+ Fälle) als Skript + CSV-Report; vor/nach jedem Deploy laufen lassen | 🟢 | Regressionsschutz, Messbarkeit | 3–4 h | ~$0.02/Lauf | — |
| P1-4 | Instructions-Feinschliff (E-Präfix-Absatz raus, Solar-Details raus) — **inhaltlich, kein Redeploy nötig** | 🟢 | Konsistenz | 15 min | 0 | Alttext wieder einsetzen (liegt im Audit vor) |

## Phase 2 — Kosten (Reihenfolge wichtig)

| ID | Maßnahme | Risiko | Nutzen | Aufwand | Kosten | Rollback |
|---|---|---|---|---|---|---|
| P2-1 | RAM/CPU-Insights prüfen → App auf `apps-s-1vcpu-0.5gb` | 🟡 | −$20/Monat | 30 min + 1 Wo Beobachtung | −20/mo | Instanz hochstufen (Minuten) |
| P2-2 | Verifizieren: neue KB ohne eigenen OpenSearch-Cluster möglich (Create-Flow, read-only ansehen) | 🟢 | Entscheidungsgrundlage | 15 min | 0 | — |
| P2-3 | Falls ja: neue KB in **FRA**, Quellen hochladen, Retrieval-Eval grün, Agent auf neue KB umhängen (bzw. neuen Agent in FRA anlegen und App-Env tauschen — Alpha am gleichen Endpoint testen) | 🟠 (Umhäng-Moment; Eval davor/danach) | Grundlage für −$19.60 + Latenz | 0.5 Tag | ~0 | alte KB bleibt bis zum Schluss bestehen → zurückhängen |
| P2-4 | **Cluster `genai-walrus` löschen** — erst nach P2-3 grün + 1 Woche Betrieb | 🔴 (endgültig; Index weg — Quelldateien existieren lokal) | **−$19.60/Monat** | 10 min | −19.60/mo | keiner (Neuaufbau aus Quelldateien ~1 h) |

## Phase 3 — Komfort (optional)

| ID | Maßnahme | Risiko | Aufwand |
|---|---|---|---|
| P3-1 | Streaming (SSE) Backend+UI | 🟡 | 0.5–1 Tag |
| P3-2 | Feedback-Persistenz (`/api/feedback` + Session-ID) | 🟢 | 2–3 h |
| P3-3 | Markdown-Headings/Links, Debug-Modus (`?debug=1`) | 🟢 | 1–2 h |
| P3-4 | Reranker aktivieren + im Eval A/B messen | 🟢 | 1 h |
| P3-5 | Statuspage-Gate von Hard-Block auf Hinweis-Banner umbauen | 🟢 | 1 h |

## Abhängigkeiten / Reihenfolge

```
P0-1 ──► P1-3 (Eval misst gegen neuen Index)
P0-3 unabhängig, so früh wie möglich (Sicherheit)
P2-2 ──► P2-3 ──► (1 Wo Betrieb) ──► P2-4
P1-1 parallel zu P2-*; Feature-Flag erlaubt gefahrloses Ausrollen
```

## Explizit NICHT vorgeschlagen

- Wechsel des Embedding-Modells oder Vector-Anbieters (Problem liegt nicht dort).
- K/Alpha-Tuning als „Fix" für Codes (Knife-Edge bleibt Knife-Edge — deterministischer Pfad löst es).
- Agent-Modellwechsel auf 120b (kein Qualitätsengpass beim Formatieren; erst nach Eval-Evidenz).
