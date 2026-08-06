# 09 — UI/UX- & Performance-Audit (Antworten auf die 25 Prüffragen)

| Frage | Befund |
|---|---|
| 1 genau eine Anfrage/Nachricht? | ✅ ja (`loading`-Flag) |
| 2 Send-Button disabled während Anfrage? | ✅ ja, Textarea ebenfalls |
| 3 Enter-Doppel? | ✅ verhindert |
| 4 kompletter Verlauf gesendet? | ⚠️ ja, ungekappt (wächst unbegrenzt) |
| 5 Request-Größe nach langen Chats | ⚠️ linear wachsend; bei 30 Turns ~15–30 KB + Tokenkosten; kappen (N=8) |
| 6 Retries? | ✅ keine (client- wie serverseitig) — keine Doppel-Antworten |
| 7 HTTP-Timeout | ⚠️ Server 90 s; Client ohne AbortController (hängt am LB-Limit) |
| 8 KB-Timeout vs. „nicht gefunden" | ❌ nicht unterschieden (Kernlücke; `retrieval_status` fehlt) |
| 9 HTTP-Fehlerbehandlung | ✅ ok (JSON-Parse-Fallback, Fehlertexte deutsch) |
| 10 robustes Response-Parsing | ✅ `_extract_content` deckt gängige Formen ab |
| 11 Citations aus realer Struktur? | ❌ falsche Felder (siehe 03/B3, F3) |
| 12 `retrieval.retrieved_data` verarbeitet? | ❌ nein — genau dort stehen `filename`/`page`/`score` |
| 13 leere Quellenbereiche ausgeblendet? | ✅ ja (inkl. `{"citations":[]}`-Altfall) |
| 14 Markdown sicher gerendert? | ✅ escape-first; ⚠️ keine Überschriften/Links, `[[C1]]`-Marker bleiben roh stehen |
| 15 Tabellen? | ✅ gerendert inkl. Scroll-Wrapper (Fix 8bc0533) |
| 16 Quellen dedupliziert? | ⚠️ `slice(0,5)` ohne Dedupe (derzeit egal, da Quellen eh leer) |
| 17 Dateiname + Seite angezeigt? | ❌ nie (Daten kommen im ungelesenen Feld) |
| 18 Debug-Modus? | ❌ nein (empfohlen: `?debug=1` zeigt request_id, latency, retrieval_status) |
| 19 Tokens nie geloggt? | ✅ korrekt |
| 20 Streaming möglich? | ✅ technisch ja (Agent-API kann `stream: true`); UI müsste SSE konsumieren — empfohlen bei 8–14-s-Antworten |
| 21 sinnvolle Ladephasen? | ⚠️ ein statischer Text + Punkte; mit Streaming obsolet |
| 22 Feedback-Buttons funktionsfähig? | ⚠️ UI ja — aber ohne Wirkung |
| 23 Feedback gespeichert? | ❌ nein (kein Endpoint, kein Storage) |
| 24 Conversation History? | Browser-Session only; Reload verwirft alles |
| 25 Session-ID? | ❌ keine (für Feedback-Zuordnung nötig) |

## Performance

- Gemessene E2E-Latenz 3,9–14,2 s (LLM-dominiert; GPT-oss-20b „denkt" ~8 s bei Reasoning-Antworten). App-Overhead vernachlässigbar → Instanz-Downsize unbedenklich.
- FRA↔TOR1-Hop: geschätzt +80–120 ms RTT pro Anfrage — gegen LLM-Latenz sekundär, aber unnötig.
- Größter wahrgenommener Gewinn: **Streaming** (Ersttoken nach ~1–2 s statt Komplettantwort nach 5–14 s).

## Konkrete UI-Verbesserungen (nach Freigabe)

1. Quellen: `retrieval.retrieved_data` → dedupliziert als „Quellen: technisches-handbuch… (S. 18)" rendern; `[[C1]]`/`C1`-Marker zu Fußnoten-Links der Quellenliste umwandeln (oder serverseitig strippen).
2. `retrieval_status` im API-Vertrag + UI-Unterscheidung „nichts gefunden" (normale Antwort) vs. „KB nicht erreichbar" (gelber Hinweis, Retry-Button).
3. Feedback: `POST /api/feedback {session_id, message_id, verdict}` → App-Platform-Log oder kleine SQLite/Spaces-Ablage; Ja/Nein-Klick bestätigen.
4. Markdown: `###`-Headings + Links ergänzen (2 Regex-Zeilen im bestehenden Renderer).
5. History clientseitig auf letzte 8 Turns kappen (mit Server-Enforcement, siehe 08/S3).
6. Streaming (SSE) als Phase 2.
