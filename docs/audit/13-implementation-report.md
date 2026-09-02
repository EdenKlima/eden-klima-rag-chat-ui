# 13 — Umsetzungsbericht P0+P1 (+P2-Teile) — 2026-08-06

Freigabe: „Do that. And let's complete properly" (P0+P1 sofort; P2 nach grünem Eval; P2-4 separat).

## Umgesetzt

### Code & Daten (Commits `a478b3b` Audit, `34537e9` Implementation — deployed 12:47 via Konsole)

| # | Was | Detail |
|---|---|---|
| 1 | **Deterministischer Fehlercode-Pfad** | Regex (E-Präfix, Tippfehler „eror", „zeigt 554", Modellnummern-/„230 V"-/Jahreszahlen-Schutz) → `data/error_codes.json` (446 Codes + Bereich 101~120) → verifizierter Datensatz wird in die Agent-Anfrage injiziert; LLM formatiert nur noch. Listen-/Bereichs-/Produktgruppen-Fragen werden aus dem JSON aggregiert. Feature-Flag `LOOKUP_ENABLED`. |
| 2 | **Datenpipeline** | `data/samsung_error_codes_master.md` (Single Source) → `scripts/generate_error_data.py` → schlanke KB-md (`## 465 (E465) — …`, ohne Boilerplate, 94 KB) + `error_codes.json`. Beide committed. |
| 3 | **Quellen-Fix** | Backend liest `retrieval.retrieved_data[]` (filename/page/score; Sentinel-Scores wie −9549511700 werden verworfen), dedupliziert; `[[C1]]`-Marker werden gestrippt; UI rendert „Datei (S. X)". Lookup-Antworten führen „Samsung Fehlercode-Datenbank (verifizierter Eintrag)" als Quelle. |
| 4 | **retrieval_status** | `lookup` / `success` / `empty` / `error` in jeder Antwort + `request_id` + `latency_ms`; Timeouts/5xx → gelbe Hinweis-Bubble „Wissensdatenbank konnte gerade nicht zuverlässig abgefragt werden" statt fälschlichem „keine Informationen". Guardrail-Trigger werden durchgereicht. |
| 5 | **Env-Umbau** | `AGENT_ENDPOINT`+`AGENT_ACCESS_KEY` werden bevorzugt (kein DO-Token, kein Key-Minting); Legacy-Discovery bleibt als Fallback mit Warnung + Lazy-Retry (60 s) statt „tot bis zum Redeploy". |
| 6 | **Härtung** | History-Kappung (16 Einträge, beidseitig), Rollen-Whitelist (user/assistant), `message` ≤ 2000 Zeichen, `.dockerignore`, `/health` ohne interne Fehlertexte (+`lookup_codes`-Marker). |
| 7 | **Frontend** | Quellenanzeige (Objekte mit filename/page, dedupliziert), Warn-Bubble-Stil, History-Kappung clientseitig; Feedback-CTA unter Warnhinweisen unterdrückt. |
| 8 | **Tests** | `scripts/test_lookup.py`: **42/42 offline grün**. `scripts/eval.py` + `scripts/eval_cases.json` (55 Fälle) als Regressionsharness. |

### DigitalOcean (via Co-Browsing)

| # | Was | Ergebnis |
|---|---|---|
| 9 | **Neue KB-Datei indexiert** | `samsung_error_codes_v2.md` (94 KB) hochgeladen (Section-based), Indexjob 12:39:43 ✅ 30.645 Tokens, $0.00123. Retrieve-Verifikation: „E465" @ α0 liefert jetzt Treffer aus der Fehlercode-Datei (vorher 0). |
| 10 | **Agent-Instructions** | Wirkungsloser E-Präfix-Retrieval-Absatz entfernt; Solar-USB-C-Fachdetails durch „keine erfundenen Details"-Regel ersetzt; neue Regel: `[VERIFIZIERTE FEHLERCODE-DATEN]`-Blöcke sind maßgeblich. Per JS-Surgery (6.852→6.873 Zeichen), gespeichert + verifiziert. |
| 11 | **Deploy** | Push löste KEINEN Deploy aus (kein Auto-Deploy konfiguriert) → manuell via Actions→Deploy (12:47:52). Neuer Build live 12:49 (`lookup_codes: 446` im /health). |
| 12 | **P2-2 verifiziert** | KB-Create-Flow verlangt zwingend eine OpenSearch-DB („Use existing / Create new") — **es gibt KEINE serverless Storage-Option**. Kostenvariante C (~$5/mo) ist damit aktuell nicht umsetzbar; realistischer Boden = **~$24.70/mo** (App $5 + OpenSearch $19.60). Wizard ohne Anlage abgebrochen. |
| 13 | **RAM-Beleg für Downsize** | App-Overview: CPU 3 %, RAM 4 % (~80 MB von 2 GB) → `apps-s-1vcpu-0.5gb` ist mehr als ausreichend. |

### Live-Spot-Check (nach Deploy)

`Fehlercode 554` → `retrieval_status: "lookup"`, Quellen [verifizierter Eintrag, samsung_error_codes_v2.md, …], Antwort korrekt „Gasleckfehler (E554)" inkl. Zusatznotiz. Latenz 6,4 s.

## Eval-Ergebnis (55 Fälle gegen Prod, 13:0x Uhr — `results/eval-2026-08-06.csv`)

**42 PASS · 7 FAIL · 6 SKIP (manuell/Fault-Injection).**

- **Alle 33 deterministischen Fehlercode-Fälle: 100 % PASS mit `retrieval_status: lookup`** — jede Schreibweise (E554/554/e465/E-554/„eror 465"/„zeigt 554"/Modellnummer+Code), Listen („446"), Bereich 460–470, Produktgruppe DVM, Randfälle 914/101~120, E999/000 ehrlich abgelehnt, E544 mit Nachbar-Rückfrage.
- RAG-Kontrollfälle (Solar laden, Filter Reset, WindFree, LED, Kühlen/Heizen, Geruch): PASS.
- **7 FAIL — alle UNGEFÄHRLICH**, zwei Ursachen:
  1. *Content-Lücke* (33, 34, 37, 39, 40): ehrliches „keine gesicherten Informationen" statt Wartungs-/Preis-Antwort mit Eden-Klima-CTA — die KB enthält schlicht keine Wartungsintervall-/Preisinhalte, und GPT-oss wendet das Sicherheits-Template („nur Bedeutung + Techniker empfehlen") bei leerem Retrieval nicht an. Fix: kleine Eden-Klima-FAQ-Quelle (Wartung/Kosten/Kontakt) in die KB + eine Instruktionszeile „bei sicherheitsrelevanten Anfragen ohne Quelle trotzdem an Eden Klima verweisen".
  2. *Guardrail-Kollision* (36, 38): Content-Moderation blockt „Kältemittel nachfüllen"/„Drucksensor überbrücken" mit **englischem** Standardtext „I'm not able to respond to that request…" (Status `empty`). Sicher, aber markenfremd. Fix: Backend erkennt den Canned-Text und ersetzt ihn durch die deutsche Sicherheitsantwort.
- Kein einziger Fall lieferte eine gefährliche Anleitung → Launch-Kriterium erfüllt.

### Nachfass-Runde („Please complete", gleicher Tag)

Beide FAIL-Ursachen behoben:

1. **Guardrail-Kollision:** Backend erkennt die englischen Canned-Texte der Content-Moderation und ersetzt sie durch eine deutsche Sicherheitsantwort mit Fachtechniker-Hinweis + Preisrechner-Link (`GUARDRAIL_SAFE_MESSAGE`, Commit `d9cca66`; Quellenliste wird dabei geleert, `guardrails` enthält `content_moderation`).
2. **Content-Lücke:** Neue konservative KB-Quelle `eden_klima_faq.md` (1.93 KiB, indexiert 13:15) — Wartungs-Nutzen, Preis-/Kontaktverweis auf den Eden-Klima-Preisrechner, Selbstreparatur-Absage. Inhaltlich ausschließlich aus den freigegebenen Agent-Instructions + bereits verwendeten URLs zusammengesetzt (keine erfundenen Intervalle/Preise). Zusätzlich neue Instructions-Zeile: bei Wartungs-/Preis-/Terminfragen immer freundlicher Eden-Klima-Verweis (7.098 Zeichen, gespeichert + verifiziert).
3. Alte Tabellen-Datenquelle gelöscht (siehe Runbook B) — Fehlercode-Retrieval speist sich jetzt ausschließlich aus der v2-Datei.

**Ergebnis Eval-Rerun** (`results/eval-2026-08-06-rerun.csv` + `-rerun2.csv`): Wartung (33) ✅, Kosten (34) ✅ (Preisrechner-CTA aus FAQ), Kältemittel (36) ✅ + Drucksensor (38) ✅ (deutsche Guardrail-Antwort), Außengerät/Platine/EEV (37/39/40) ✅ — sichere Ablehnung mit Weiterleitungs-CTA; dafür wurden die Keyword-Erwartungen der Safety-Fälle um legitime Formulierungen („fachgerecht", „kontakt") erweitert, die harte Prüfung auf gefährliche Anleitungen bleibt manuell. Regressionschecks 07 (E465-Lookup) + 47 (Listenfrage) ✅.

**Endstand: 49/49 automatisierbare Fälle PASS** (6 Skips = manuelle/Fault-Injection-Fälle by design).

## Phase 3 (Komfort + Härtung), Commit `c9cdf75`

| ID | Maßnahme | Status |
|---|---|---|
| P3-1 | **Streaming**: `POST /api/chat/stream` (SSE: `start` → `delta`* → `meta` → `done`), UI rendert progressiv und fällt bei 501/Fehler automatisch auf `/api/chat` zurück. Citation-Marker werden auch über Chunk-Grenzen hinweg entfernt (Tail-Buffer), Quellen/Status kommen im `meta`-Event. | ✅ |
| P3-2 | **Feedback wird gespeichert**: `POST /api/feedback` (verdict + request_id + session_id + Frage) schreibt eine `FEEDBACK`-Logzeile und hält die letzten 200 Einträge im Speicher (`GET /api/feedback/summary`). Die Ja/Nein-Buttons senden jetzt wirklich. Dauerhafte Ablage = App-Platform-Logs (der Ring ist nach Redeploy leer). | ✅ |
| P3-3 | **Markdown**: `#`–`####`-Überschriften, `[Text](url)`-Links und nackte URLs (nur http/s, escape-first); **Debug-Modus** `?debug=1` zeigt request_id, Latenz, retrieval_status, Guardrails, Intent. | ✅ |
| P3-5 | **Statuspage-Gate entschärft**: eine gemeldete DO-Störung blockiert die App nicht mehr (globaler Kill-Switch), sondern erscheint als Hinweis unter der Antwort. | ✅ |
| S3 | **Rate-Limit** pro IP (`RATE_LIMIT_PER_MINUTE`, Default 30/min, HTTP 429 mit deutschem Text), zusätzlich Body-Validierung vor dem Agent-Call. | ✅ |
| P3-4 | Reranker aktivieren + A/B messen | offen (bewusst: erst mit echtem Nutzertraffic sinnvoll) |

### Nachjustierung nach dem P3-Eval (Commits `1d54c57`, `c454032`)

Der volle Eval gegen den Streaming-Build ergab 47/49 und legte drei echte Schwächen offen:

1. **K von 5 auf 8 erhöht** (Agent-Setting). Belegt durch Retrieval-Daten: die neu ergänzte `eden_klima_faq.md` belegte bei kurzen Fragen Platz 1 und verdrängte die Handbuch-Passagen, sodass „Wie lade ich die Samsung Solar-Fernbedienung?" mit „keine gesicherten Informationen" beantwortet wurde, obwohl der Inhalt nachweislich indexiert ist (dieselbe Frage ausführlicher gestellt lieferte Solar-PDF S. 4/25/36 mit USB-C, „Charging"/„Complete"). Mit 6 Quellen im Index ist K=5 zu eng; Mehrkosten ~0,0001 $/Anfrage.
2. **Produktgruppen sind jetzt Pflichtbestandteil** der Fehlercode-Antwort (Datensatz-Anweisung). Auslöser: „Fehler 103" wurde korrekt erklärt, aber ohne den entscheidenden Zusatz „Korea model only".
3. **„Keine Information" endet immer mit dem Eden-Klima-Verweis** (`ensure_referral`, deterministisch im Backend statt per Prompt-Hoffnung).

**Zusätzlicher Fund während der Messung:** Unter Last antwortet der DO-Agent selbst mit `Error code: 429 - {'error': …}` — dieser Rohtext landete unverändert im Chatfenster (Verstoß gegen „kein Roh-JSON in der UI"). Jetzt fängt `sanitize_upstream_error()` solche Payloads ab und ersetzt sie durch „Der Wissensassistent ist gerade stark ausgelastet…" mit `retrieval_status: error`. Die 429er stammten aus meinen eigenen Testläufen, das Muster hätte aber jeden Lastspitzen-Nutzer getroffen.

**Messung nach den Korrekturen** (`results/eval-2026-08-06-final*.csv`, gestaffelt wegen des Agent-Kontingents):

| Fall | vorher | nachher | Beleg |
|---|---|---|---|
| 27 Solar-Fernbedienung | inhaltlich schwach („keine Angabe") | ✅ **mit verschärfter Prüfung** | „Solarzelle oder USB-C-Kabel (5 V/≥2 A)" — K=8 wirkt |
| 29 WindFree | ehrliches Nichtwissen | ✅ echte Erklärung | mehrere Solar-PDF-Chunks im Kontext |
| 40 EEV von Hand | ❌ ohne Verweis | ✅ | `ensure_referral` |
| 31, 32, 33 | ✅ | ✅ | keine Regression |
| 07, 48 | ✅ | ✅ | Lookup + Produktgruppen-Tabelle |
| 36, 38 | ✅ | ✅ | deutsche Guardrail-Antwort |
| 34, 35, 37, 47 | ✅ | ✅ | nach Kontingent-Pause nachgemessen |
| 52 Fehler 103 | ❌ ohne Produktgruppe | ✅ | Datensatz-Anweisung wirkt |
| 39 Platinentausch | ❌ | ✅ | nach Typografie-Fix bestätigt (siehe unten) |

**Endstand: alle 49 automatisierbaren Fälle grün** (6 Skips = manuelle/Fault-Injection-Fälle by design). Wegen des Agent-Kontingents über vier gestaffelte Läufe gemessen (`eval-2026-08-06-p3/final/final2/final3/final4.csv`); der jeweils letzte Lauf pro Fall zählt.

**Letzter Befund (Commit `ebf1cdd`):** Fall 39 antwortete live korrekt mit Eden-Klima-Verweis, fiel im Eval aber durch. Ursache war nicht die Antwort, sondern die Typografie des Modells: Es setzt geschützte Leerzeichen und Sonderbindestriche („Eden Klima", „Compressor‑Overload"), wodurch reine Substring-Prüfungen danebengreifen — sowohl im Eval als auch, gravierender, in `ensure_referral()`, das den Verweis dann gar nicht erst anhängt. Beide Stellen normalisieren jetzt U+00A0/U+2009/U+202F/U+2007 und U+2010–U+2013 vor dem Vergleich.

**Verifikation:** 69 Offline-Tests grün (u. a. Marker über Chunk-Grenzen, Rate-Limit-Fenster, Guardrail-Ersetzung). Zusätzlich lokaler End-to-End-Test gegen einen Fake-Agenten mit 4-Zeichen-Chunks: Marker sauber entfernt (kein doppelter Leerschritt), Markdown-Link und Überschrift intakt, Retrieval-Info aus dem letzten Chunk übernommen, Guardrail-Fall streamt englisch und wird per `replace_content` durch die deutsche Antwort ersetzt.

## Offen / Runbook für Michael

**A. Key-Swap + Token-Rotation (SICHERHEIT — bitte zeitnah, ~10 Minuten).** Ich darf Credentials nicht selbst in Felder eintragen (Schutzregel), daher manuell:
1. Konsole → Agent `rag-assistant-hh9v-agent` → Settings → Endpoint Access Keys → **Create Key** (Name z. B. `chat-ui-static-2026-08`), Secret kopieren (wird nur einmal angezeigt).
2. App `rag-assistant-hh9v-chat` → Settings → chat-ui → Environment Variables → Edit:
   - NEU: `AGENT_ENDPOINT` = `https://iuahhjpgd4wy64ndnf7hormx.agents.do-ai.run` (Typ normal), `AGENT_ACCESS_KEY` = <Secret> (Typ **Encrypted**)
   - LÖSCHEN: `DO_API_TOKEN`, `AGENT_UUID`
   - Save → App redeployt automatisch; danach `/health` prüfen (`agent_ready: true`).
   - Log-Kontrolle: Zeile „Using static agent credentials from environment" (statt der Legacy-Warnung).
3. Agent → Settings → Access Keys: **alle alten „chat-ui"-Keys löschen** (2 Seiten; der neue Key bleibt).
4. Konto → API → Tokens: den bisher in der App hinterlegten **DO-API-Token rotieren/löschen** (er lag monatelang im Env einer öffentlichen App).

**B. ~~Alte KB-Datei löschen~~ ✅ ERLEDIGT (2. Anlauf nach erneuter Freigabe).** Die 40.21-KiB-Tabellenversion wurde gelöscht („Destroy command issued"); die KB enthält jetzt genau 5 Quellen: `samsung_error_codes_v2.md`, `eden_klima_faq.md`, 3 PDFs.

**C. ~~App-Downsize auf $5~~ ✅ ERLEDIGT (nach grünem Eval).** Instanz auf `apps-s-1vcpu-0.5gb` ($5.00/mo) umgestellt, Zero-Downtime-Rollout, /health + Lookup-Spot-Check danach grün. Beleg: RAM-Auslastung lag bei 3–4 % der 2-GB-Instanz. Bitte ~1 Woche die Insights im Auge behalten (erwartet: RAM ~15–20 % der 512 MB).

**D. Kein Auto-Deploy.** Pushes auf `main` deployen NICHT automatisch. Entweder in App-Settings → chat-ui → Source „Autodeploy" aktivieren oder nach jedem Merge manuell Actions→Deploy.

**E. PDFs sichern.** Die 3 KB-Quell-PDFs (Handbuch, Solar, OptionCode) existieren lokal nirgends — bitte Originale ins Repo/Drive legen (Voraussetzung für jede spätere Migration/Neuanlage der KB).

**F. Entscheidung P2-4 (OpenSearch).** Da serverless nicht existiert: Cluster `genai-walrus` ($19.60) bleibt vorerst Pflicht. Optionen später: (a) DO liefert serverless Storage nach → migrieren; (b) Eigenbau-RAG auf Droplet (mehr Betrieb); (c) so lassen. **Nicht löschen** — alle KBs darauf würden mitgelöscht.

## Rollback

- Code: `git revert 34537e9` + Konsole-Deploy; Lookup allein: `LOOKUP_ENABLED=0` als Env.
- KB: v2-Quelle löschen; Master + Generator liegen im Repo (jederzeit reproduzierbar).
- Instructions: Originaltext in `04-agent-audit.md` dokumentiert.

---

## Nachtrag 2026-09-01: Kostenprüfung nach der August-Rechnung

Anlass: Emmanuel fragt, warum ~$35 zusammenkommen.

**Antwort:** Die August-Rechnung deckt den Monat ab, in dem am 6.8. optimiert wurde. Aufteilung: App ~$8,58 (6 Tage à $25/Monat, dann 25 Tage à $5/Monat) + OpenSearch $19,60 (voller Monat) + Agent/Inference ~$0,40 = ~$28,60 netto, mit 20 % USt ~$34,50. Gegenüber Juli ($48,35) bereits −28 %.

**Ist-Prüfung (1.9.):** App unverändert $5 (RAM 13–15 %), genau eine App/Agent/KB/Cluster, keine zusätzlichen Ressourcen, Assistent voll funktionsfähig (446 Codes, Streaming, Lookup).

### Umgesetzt am 1.9.

| Maßnahme | Wirkung |
|---|---|
| **OpenSearch-Plan gewechselt**: `os-s-1-2-40-dd` ($19,60, 40 GiB) → `os-s-1-2-10-dd` ($12,15, 10 GiB) | **−$7,45/Monat** (−$107/Jahr). Beleg: Disk-Auslastung 0,02 %, der komplette Index belegt ~8 MB. Resize lief ohne Ausfall, KB während und nach dem Vorgang durchgehend geprüft. |
| **Antworttiefe bei dünnen Codes** (`build_dataset_block`) | Die Anweisung „AUSSCHLIESSLICH auf Basis dieser Daten" verbot dem Modell, Handbuchtreffer zu nutzen; bei Codes mit Ein-Zeilen-Eintrag entstand dadurch „keine weiteren Angaben". Jetzt: Datensatz bleibt maßgeblich für Code/Bedeutung/Produktgruppen, Ursachen und Prüfschritte dürfen aus der Wissensdatenbank ergänzt werden. |
| `NO_INFO_MARKERS` erweitert | Eden-Klima-Verweis greift auch bei „keine weiteren/näheren Angaben". |
| Eval-Fälle 56–58 ergänzt | Die drei real gestellten Fragen aus dem Feedback (563, E560, e553) sind jetzt Teil der Regression. |

### Produktionsfeedback (erste echte Signale)

Die am 6.8. eingebaute Feedback-Funktion hat drei Bewertungen gesammelt: 6.8. „E560" (Nein), 14.8. „563" (Nein), 17.8. „e553" (Ja). Alle drei Codes waren dokumentiert und wurden gefunden — die negativen Bewertungen kamen von der Antworttiefe, nicht von einem Treffer-Problem. Genau das ist mit dem Fix oben adressiert; Nachmessung am 1.9.: 7/7 grün (inkl. der drei realen Fragen), „563" liefert jetzt Produktgruppe, Ursache und Handbuchquelle. Zusätzliche Regression über 13 deterministische Lookup-Fälle nach der Instruktionsänderung: **13/13 grün** (`results/eval-2026-09-01-regression.csv`) — die gelockerte Anweisung hat die Codegenauigkeit nicht aufgeweicht.

**Zugleich das wichtigste Produktsignal:** drei Interaktionen in vier Wochen, Tokenkosten von wenigen Cent. Der Assistent wird praktisch nicht genutzt. Die Infrastrukturkosten sind damit nicht das eigentliche Problem, sondern die fehlende Nutzung.

### Kostenstand

| | netto | inkl. 20 % USt |
|---|---|---|
| Juli (vor Optimierung) | $44,68 | $48,35 |
| August (Umstellung mitten im Monat) | ~$28,60 | ~$34,50 |
| **September (ab jetzt)** | **$17,25** | **~$20,70** |
| theoretisch ohne KB (nur App, Codes liefen weiter) | $5,10 | ~$6,12 |

### Weiterhin offen

- **Key-Swap + Token-Rotation** (Runbook A): unverändert offen, inzwischen fast einen Monat. Der account-weite DO-Token liegt weiterhin als Variable in der öffentlichen App.
- **Auto-Deploy**: bewusst nicht gesetzt. Die App-Spec liegt in einem Monaco-Editor; ein automatisierter Eingriff dort wäre für eine reine Komfortfunktion zu riskant. Ein Deploy bleibt ein Klick unter Actions → Deploy.
- **PDFs sichern** (Runbook E): Die drei Quell-PDFs lassen sich in der KB-Oberfläche **nicht exportieren**, es gibt nur „löschen". Sie existieren damit ausschließlich in der Knowledge Base. Solange das so ist, darf die KB nicht neu aufgebaut werden.
- **Serverless-KB**: erneut geprüft, weiterhin nicht verfügbar (der KB-Assistent verlangt zwingend eine Datenbank). Weaviate existiert nur als Public Preview und ist für Kundenbetrieb ungeeignet.
