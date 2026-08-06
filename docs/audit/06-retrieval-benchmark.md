# 06 — Retrieval-Benchmark (live gemessen, 2026-08-06)

Rohdaten: `results/retrieval-tests.csv` · E2E-Antworten: Session-Scratchpad `e2e/results.jsonl`
Kanäle: **A** = öffentliche App `/api/chat` (voller Stack) · **K** = kbaas-Retrieve-Playground (Konsole, isoliertes Retrieval) · **P** = Agent-Playground (Konsole)

## Kernmatrix

| Query | Kanal | Alpha | Ergebnis |
|---|---|---|---|
| Compressor overload error | K | 0 | ✅ 5/5 Treffer = md-TableChunks, Rang 1 enthält 464+465 (2144 ms) |
| error 465 | K | 0.5 | ✅ Rang 1+2 = md-TableChunks (1360 ms) |
| E465 | K | 0 | ❌ nur 2 Treffer im ganzen Index, beide PDF S. 69 — „E465" existiert als Token nur im PDF, nie in der md (603 ms) |
| Was bedeutet Fehler 465? | K | 0.5 | ❌ 5/5 Treffer = Handbuch-PDF (S. 18/19/20/40/70, CompositeElement), md unsichtbar (700 ms) |
| error 464 / error 465 / 465 / E465 / Was bedeutet Fehler 464? | A | Agent-Default | ❌ alle: „keine gesicherten Informationen" (09:33–09:40) |
| Compressor overload error · Gas leak error | A | Agent-Default | ❌ Ablehnung trotz wortgleicher Zeile im Index |
| Was bedeutet der Fehler E554? | A | — | ⚠️ Antwort **falsch** (Kommunikationsfehler statt Kältemittelmangel), Zitat = irrelevanter Fernbedienungs-Chunk |
| Fehlercode 554 | A | — | ✅ inhaltlich richtig (Kältemittelmangel, via Handbuch), Zitat erneut irrelevanter Chunk |
| Welche Fehlercodes kennst du? / für DVM? | A | — | ❌ strukturell: nennt nur EIO1/E554/E422 (PDF-Funde); K=5-RAG kann 446 Codes nicht aufzählen |
| Wie lade ich die Samsung Solar-Fernbedienung? | A | — | ✅ korrekt, Quelle Solar-PDF (Kontrollfall normales RAG) |
| Was bedeutet der Fehler E999? | A | — | ✅ korrekt abgelehnt (keine Halluzination) |
| Was bedeutet der Fehler 108? | A | — | ❌ Ablehnung (Code im Index vorhanden) |
| error 465 | P | Agent-Default | ✅ korrekt inkl. C1-Zitat — **dieselbe Query, die 25 min zuvor via App scheiterte** |

## Interpretation

1. **Strukturell (reproduzierbar):**
   - E-Präfix-Queries können die md nie treffen (Datei schreibt nur „465"); Treffer gibt es nur, wenn zufällig das PDF den E-Code führt (E554/E422/E201 → daher deren „Funktionieren").
   - Deutsche Formulierungen @ Hybrid α≈0.5: semantischer Anteil zieht die deutschen PDF-Chunks vor die englisch-nummerischen TableChunks — 0/5 md-Treffer.
   - Listenfragen sind mit K=5-RAG prinzipiell unbeantwortbar (Retrieval ist keine Datenbankabfrage).
   - Englische Roh-Queries („error 465") funktionieren sogar hybrid — der Normalnutzer stellt sie nur nicht.
2. **Transient (nicht reproduzierbar):** identische Query via App (09:33) fehl, via Konsole (09:57) korrekt; kein Indexlauf dazwischen (Activity: letzter echter Job 30.06.). Kandidaten: approximatives kNN + Hybrid-Fusion am Knife-Edge, kurzzeitige KB-/Agent-Degradation (dokumentierter Incident 1.–2.7. im ursprünglichen Testzeitraum; heutiges Fenster nicht attributierbar — Agent-Logs/Observability wären der nächste Schritt). Merksatz fürs Design: **Codes nie vom Knife-Edge abhängig machen.**
3. **Score-Sentinel:** `-9549511700` erscheint wörtlich als Beispiel-`score` in der offiziellen Response-Doku → Plattform-Platzhalter (v. a. bei Keyword-only-Treffern/Parent-Chunks), kein lokaler Bug. Nicht für Ranking-Logik verwenden; `retrieval.retrieved_data`-Reihenfolge ist maßgeblich.

## Nicht ausgeführte Zellen des Prompts-Testplans

Alpha 0.3/0.7/1.0 × num_results 3/8/10 × alle Code-Varianten sowie `item_name`-Filtertests wurden **nicht** vollständig durchgemessen (Konsolen-Roundtrips; Erkenntnisgewinn nach den vier Kernzellen gering). Vollautomatisierbar nach Freigabe via Retrieve-API — Protokoll:

```bash
# Voraussetzung: DO-Token mit Scope GenAI:read (Settings → API → Tokens), NIE ins Repo
curl -sS https://kbaas.do-ai.run/v1/479333ec-749c-11f1-aee4-4e013e2ddde4/retrieve \
  -H "Authorization: Bearer $DO_GENAI_READ_TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"error 465","num_results":5,"alpha":0,
       "filters":{"and_all":[{"field":"item_name","operator":"equals","value":"samsung_air_conditioner_error_codes.md"}]}}'
```

Der Testplan in `12-test-plan.md` enthält die vollständige Matrix (Queries × α ∈ {0, 0.3, 0.5, 0.7, 1} × k ∈ {3, 5, 8, 10} × Filter on/off) als Skriptvorlage.
