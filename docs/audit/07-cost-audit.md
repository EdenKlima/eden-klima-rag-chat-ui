# 07 — Kosten-Audit

Ist (Juli-Rechnung, Details in `02` + `results/cost-comparison.csv`): **$44.68** Nutzung → **$48.35** inkl. USt. Davon $44.60 Fixinfrastruktur, $0.08 Modellnutzung. **Token-Kosten sind irrelevant — der Hebel liegt ausschließlich bei App-Instanz und OpenSearch.**

## 1) App Platform: $25 → $5

- Ist: `apps-s-1vcpu-2gb` ($25) für einen FastAPI-Proxy + statisches HTML. RAM-Bedarf der App: FastAPI+uvicorn+httpx erfahrungsgemäß 80–150 MB; keine In-Memory-Daten außer index.html (27 KB).
- Verifizierte Preisstufen: 512 MiB $5 · 1 GiB fixed $10 · 1 GiB $12 · 2 GiB $25.
- Empfehlung: **`apps-s-1vcpu-0.5gb` ($5)**. Belastbarkeit vor dem Downsize messen (App-Platform-Insights: RAM/CPU; danach 1 Woche beobachten). Boot-Zeit/Latenz unkritisch (ein Prozess, kein Build-Heavy-Lifting). Rollback = Instanz wieder hochstufen (Minuten, kein Datenverlust).
- Nebenschauplatz „professional"-Tier: prüfen, ob Features (z. B. mehrere Instanzen) gebraucht werden — für den Piloten reicht die kleinste Stufe.

## 2) OpenSearch: $19.60 — der eigentliche Block

- **Korrektur einer Annahme aus dem Auftrag:** Die 40 GiB sind kein optionales Extra, sondern das **Plan-Minimum** des Basic-2GB/1vCPU-Tiers (Range 40–200 GiB; $11 Node + $8.60 Storage = $19.60 Listenpreis). „40 GiB reduzieren" ist **nicht möglich**; ein kleinerer OpenSearch-Plan existiert nicht.
- Tatsächlicher Bedarf: 4 Quellen, 11.58 MiB Rohdaten, ~68k Index-Tokens — der Cluster ist zu >99 % leer.
- **Der echte Hebel: DigitalOceans serverless Knowledge-Base-Storage (kbaas).** Die KB-Produktlinie rechnet inzwischen nach Embedding-Tokens ab (Qwen3 0.6B $0.04/1M; Reranking optional $0.01/1M) statt einen Kundencluster zu verlangen. Diese KB (Ende Juni erstellt) hängt noch am eigenen Cluster `genai-walrus`. Zu verifizieren (Teil des Plans, read-only im Create-Flow prüfbar): ob eine **neue** KB ohne eigenen Cluster erstellt werden kann. Falls ja: neue KB (FRA!) → Quellen erneut hochladen (Minuten, ~$0.005) → Agent umhängen → alten Cluster löschen = **−$19.60/Monat**.
- Downgrade-Regeln (falls Cluster bleiben soll): Scale-down erlaubt bei ≤80 % projizierter Auslastung — hier locker erfüllt, aber es gibt keinen günstigeren Zielplan, also irrelevant.
- **Achtung Reihenfolge:** KB-Destroy löscht den Cluster NICHT mit; Cluster erst löschen, wenn die neue KB nachweislich funktioniert (Retrieval-Regressionstest grün).

## 3) Modelle/Guardrails (keine Aktion nötig)

GPT-oss-20b $0.05/M in · $0.45/M out; Juli gesamt $0.04. Moderation+Jailbreak ~$0.01. Auch 100× Traffic bliebe <$10/Monat. Reranker-Zuschaltung: +~$0.01/Monat beim Pilotvolumen.

## Kostenvarianten (vor USt)

| Variante | App | Vector/KB | Tokens | Summe/Monat |
|---|---|---|---|---|
| **A** Ist | 25.00 | 19.60 (OpenSearch) | 0.08 | **44.68** |
| **B** optimierter DO-Pilot | 5.00 | 19.60 | ~0.10 | **~24.70** |
| **C** Low-Cost DO (serverless KB) | 5.00 | ~0.05 (Embedding-Tokens) | ~0.10 | **~5.15** |

Alternativen außerhalb DO (der Vollständigkeit halber, Details bewusst knapp — C erfüllt das Ziel bereits):

| Option | Fix $/Monat | Betrieb | Qualität | Lock-in | Einschätzung |
|---|---|---|---|---|---|
| C (DO serverless KB) | ~5 | minimal | unverändert (gleiche Engine) | DO | **empfohlen** |
| Droplet + pgvector/Chroma + eigener RAG-Code | 6–12 | hoch (selbst warten) | selbst zu bauen | gering | nur bei DO-Exit sinnvoll |
| Externe Vector-SaaS (Qdrant Cloud free, Weaviate …) | 0–25 | mittel | gut | mittel | Für Fehlercodes overkill — der Lookup braucht **gar keinen** Vektorstore |
| Fehlercode-Lookup als JSON im App-Container | 0 | null | deterministisch, besser als RAG | keiner | **Teil der Zielarchitektur, unabhängig von A/B/C** |

Erwartete Zielkosten nach Umsetzung C: **~$5–6/Monat inkl. USt** bei Pilot-Traffic; Backups/Logging über Plattform-Standards abgedeckt, kein separater Posten.
