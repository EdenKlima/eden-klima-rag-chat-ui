# 05 — Knowledge-Base-Audit (rag-assistant-hh9v-kb)

## Datenquellen (Konsole, 2026-08-06)

| Datei | Größe | Chunking | Zuletzt indexiert | Status |
|---|---|---|---|---|
| samsung_air_conditioner_error_codes.md | **40.21 KiB** | Section-based | 30.06. (Job 19:52:30, 10.340 Tokens, $0.00041) | Completed |
| technisches-handbuch-samsung-samcool.pdf | 7.65 MiB | Hierarchical | 30.06. (Job 19:20, 3 Dateien, 58k Tokens) | Completed |
| IR Fernbedienung Solar.pdf | 800.73 KiB | Hierarchical | 30.06. | Completed |
| OptionCode Setting.pdf | 3.11 MiB | Hierarchical | 30.06. | Completed |

Auto-Indexing: wöchentlich Do 12:00 UTC. Letzter Lauf heute: „No Changes Detected". Seit 30.06. wurde **nichts** neu indexiert.

## Hauptbefund: veraltete Fehlercode-Datei

- **Indexiert**: die ursprüngliche **Tabellenversion** (40,21 KiB ≈ 10,3k Tokens). Der Chunker hat sie in `TableChunk`s zerlegt (mehrere Codes pro Chunk, z. B. ein Chunk „450…469" mit 464+465; live verifizierte Chunk-Bereiche: 257–271, 347–399, 400–422, 450–469, 470–496). Alle ~446 Codes sind als kompakte Zeilen `<code> <message> - <Produktgruppen>` enthalten.
- **Nicht hochgeladen**: die lokale RAG-optimierte **Abschnittsversion** `/Users/michael/Documents/samsung_air_conditioner_error_codes.md` (372,5 KiB, 12.540 Zeilen, 447 `##`-Sektionen, finalisiert 30.06. 21:02 — **69 Minuten nach dem letzten Indexlauf**). Identische Kopie in `~/Downloads`.
- Konsequenz: Die im Projektkontext beschriebene „RAG-freundliche Struktur" (Customer-safe summary, Technician note je Code) existiert **nur lokal**; das Retrieval arbeitet auf Zahlen-Tabellen-Chunks, die semantisch kaum unterscheidbar und für deutsche Queries unsichtbar sind (Benchmark: `06`).

## Analyse der lokalen Abschnittsversion (vor Re-Upload zu beheben)

Skript-geprüft (447 Sektionen):

| Prüfung | Ergebnis |
|---|---|
| Codes | 446 Einzelcodes (101–914) + 1 Bereichsheading `101~120` · keine Duplikate · 460–470 lückenlos |
| Sektionen | min 618 / median 808 / max 1704 Zeichen (~155–430 Tokens) — passt in Section-Chunks ≤512 |
| Encoding | UTF-8, kein BOM, keine CRLF, keine U+2028/2029 ✓ |
| E-Präfix | **0 Vorkommen** von „E464"-Schreibweisen — Queries mit E-Präfix können per BM25 nie matchen |
| Boilerplate | **Alle 447 Sektionen enthalten denselben Satz** („…Den angezeigten Code notieren…"); Technician note wiederholt nur die Quellfelder → Embeddings der Sektionen werden nahezu identisch; Codes unterscheiden sich fast nur durch die Zahl |
| Inhaltsquelle | Customer-safe summaries sind generisch generiert (kein Fachinhalt jenseits der Originalfelder) — kein Faktenrisiko, aber auch kein Mehrwert |
| Range-Codes | `101~120` überlappt die Einzelcodes 101–109 (Dublette im Ranking, klein) |

**Empfehlung Dateiformat (für Freigabe vorbereitet):** je Code eine kompakte Sektion mit beiden Schreibweisen im Titel (`## 465 (E465) — Compressor overload error`), Feldern Code/E-Code/Message/Produktgruppen/Hinweis — **ohne** identischen Boilerplate (der gehört als Template ins Backend/LLM, nicht in jeden Chunk). Zusätzlich dieselben Daten als `error_codes.json` für den deterministischen Lookup (Single Source: die md generiert das JSON).

## Widerspruch zwischen Quellen

Handbuch-PDF S. 20: „Wann wird E422 festgestellt? Wenn gar kein Kältemittel im System…" vs. Tabellenversion „422 — EEV close error (self diagnosis)". Fachlich verwandt (Selbstdiagnose des EEV bei fehlendem Kältemitteldurchfluss), aber die Antworten variieren je nach Trefferquelle. Für Codes, die in beiden Quellen vorkommen (201, 422, 554 …), muss der Lookup die **kanonische** Quelle (Fehlercode-Datei) priorisieren; das Handbuch bleibt Kontextlieferant.

## Infrastruktur

- Embedding: Qwen3 Embedding 0.6B ($0.04/1M) — mehrsprachig, klein; für nummernlastige Near-Duplicates prinzipbedingt schwach → deterministischer Lookup wichtiger als Modellwechsel.
- Reranker: **nicht konfiguriert** (Konsole-Hinweis aktiv). Option: BGE Reranker v2 m3 ($0.01/1M) — hebt Keyword-Treffer in Hybrid-Ranking; erst nach Re-Upload evaluieren.
- Storage: OpenSearch `genai-walrus` (TOR1, Basic 2 GB/1 vCPU, 40 GiB Minimum, $19.60). Hinweis Konsole: KB-Destroy löscht den Cluster **nicht** mit (separater Schritt; Reihenfolge bei Migration beachten).
- Retrieve-API: `POST https://kbaas.do-ai.run/v1/479333ec-…/retrieve` mit `query`, `num_results` (0–100), `alpha` (0=BM25 … 1=Vektor), `reranking.enabled`, `filters` (`item_name`, `file_id`, `page_number`, `chunk_category`; Operatoren equals/starts_with/wildcard/…; `and_all`/`or_all`) — Token-Scope `GenAI:read` genügt. Damit ist ein gezielter Datei-Filter auf die Fehlercode-Datei **serverseitig möglich**.
