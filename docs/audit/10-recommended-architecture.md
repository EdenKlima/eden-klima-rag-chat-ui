# 10 — Empfohlene Zielarchitektur

## Grundsatz

Fehlercodes sind **strukturierte Schlüssel**, keine semantischen Wissensfragen. Ein Code-Lookup darf nie davon abhängen, ob eine Vektorsuche den richtigen von 446 nahezu identischen Chunks in die Top-5 hebt. RAG bleibt für alles Erklärende (Handbücher, Fernbedienung, Wartung).

## Zwei Pfade im FastAPI-Backend

```
Nutzerfrage
  │
  ├─ Regex erkennt Code?  (?i)\b(?:fehler(?:code)?|error|code|e)?\s*[-.:]?\s*E?(\d{3})\b
  │        │ ja                                    (+ Bereichslogik 101~120, Mehrfachcodes)
  │        ▼
  │   PFAD 1 — DETERMINISTISCH
  │   error_codes.json (aus der md generiert, im Container gebündelt)
  │   ├─ Treffer → Datensatz {code, e_code, message, produktgruppen, hinweis}
  │   │            → Agent-Aufruf MIT eingebettetem Datensatz im User-Turn:
  │   │              „Beantworte auf Basis dieses verifizierten Datensatzes: …"
  │   │              (LLM übersetzt/formatiert nur noch; Retrieval liefert Zusatzkontext,
  │   │               darf aber nicht widersprechen — kanonische Quelle ist der Datensatz)
  │   └─ kein Treffer → ehrliches „Code unbekannt" + Nachbarcode-Vorschlag (aus JSON, nicht vom LLM)
  │
  └─ sonst
      PFAD 2 — RAG wie bisher
      Agent (Hybrid, K=5) über PDFs + neue Abschnitts-md; optional Reranker
```

Warum LLM im Pfad 1 behalten: Sprachspiegelung (DE/EN/…), kundensichere Formulierung, Sicherheits-Template — aber grounded auf exakt einem verifizierten Datensatz ⇒ Halluzinationsrisiko ~0, Latenz sinkt (kein Retrieval-Roulette), Antwort deterministisch reproduzierbar.

Optionaler Zwischenschritt (wenn ohne Code-Deploy gewünscht): Retrieve-API mit `alpha: 0` + Filter `item_name = samsung_air_conditioner_error_codes.md` als exakter Fetch — funktioniert laut Benchmark, bleibt aber von kbaas-Verfügbarkeit abhängig. Die JSON-Variante ist robuster und $0.

## Datenbasis

1. **Fehlercode-Master bleibt die md** (Single Source of Truth, versioniert im Repo z. B. `data/samsung_error_codes.md`).
2. Build-Schritt generiert daraus `error_codes.json` (Skript im Repo; läuft im Docker-Build).
3. **Neue Abschnittsversion vor Upload entschlacken** (siehe 05): Titel `## 465 (E465) — Compressor overload error` (beide Schreibweisen → BM25 matcht künftig auch „E465"), ohne 447× identischen Boilerplate; Customer-Template rendert das Backend/LLM.
4. KB-Quellen danach: 3 PDFs (hierarchisch, unverändert) + neue md (section-based). Alte Tabellenversion ersetzen.

## Listen-/Aggregatfragen („Welche Codes kennst du?", „Codes für DVM?")

Pfad-1-Erweiterung: Regex-Intents (`welche codes|liste|zwischen X und Y|für <Produktgruppe>`) → Aggregation direkt aus `error_codes.json` (Zählung, Bereichsfilter, Gruppenfilter) → LLM fasst zusammen („446 Codes dokumentiert, z. B. …"). Nie über RAG beantworten.

## Plattform-Setup (Ziel)

| Baustein | Ziel |
|---|---|
| App | `apps-s-1vcpu-0.5gb`, FRA, Env nur `AGENT_ENDPOINT`+`AGENT_ACCESS_KEY` |
| Agent | GPT-oss-20b, Temp 0.2, K=5, Method None, Citations on — **bei Neuanlage Region FRA** |
| KB | serverless (kbaas) statt Cluster-gebunden, Region FRA, Qwen3 0.6B; Reranker BGE v2 m3 einschalten und im Eval messen |
| OpenSearch `genai-walrus` | nach verifizierter Migration **löschen** (−$19.60) |
| Instructions | 2 Korrekturen: E-Präfix-Absatz streichen (macht jetzt das Backend), Solar-USB-C-Fachdetails raus; Rest bleibt |
| Timeout-Handling | Backend liest `retrieval`-Feld: leer+Fehler ⇒ `retrieval_status=timeout` ⇒ UI-Hinweis „Wissensdatenbank gerade nicht erreichbar" statt „liegen keine Informationen vor" |

## Erwartete Wirkung (gegen Benchmark verifizierbar)

| Fall | heute | Ziel |
|---|---|---|
| 465 / E465 / „Was bedeutet Fehler 465?" (alle Schreibweisen) | 0–20 % Trefferquote, nicht deterministisch | 100 %, deterministisch, <3 s |
| Welche Codes …? / Bereich / Produktgruppe | strukturell falsch | vollständig aus JSON |
| E999 (unbekannt) | korrekt abgelehnt | korrekt + „meinten Sie 999-Nachbarn?" aus JSON |
| Fernbedienung/Wartung (RAG) | gut | unverändert gut, + echte Quellenanzeige |
| Fixkosten | $44.68 | ~$5.15 (Variante C) |
