# 04 — Agent-Audit (rag-assistant-hh9v-agent, Konsole 2026-08-06)

## Ist-Konfiguration (verifiziert)

| Parameter | Wert | Bewertung |
|---|---|---|
| Foundation-Modell | OpenAI GPT-oss-20b (Reasoning, „thinking" ~8 s beobachtet) | ok für Pilot; 120b nur bei Bedarf |
| Max Tokens | 1536 | ok (längste Antwort 1297 Tokens — nahe am Limit, beobachten) |
| Temperature | 0.2 | ok |
| Top P | 0.8 | ok |
| K Value | 5 | ok als Default; für PDFs mit Parent-Chunks eher 3–5 als 8–10 (Kontextkosten ~6,9k Tokens/Anfrage schon jetzt) |
| Retrieval Method | **None** („uses the original query as-is") | ok — kein Rewrite; damit ist die Query-Normalisierung Aufgabe des Backends |
| Alpha | **nicht konfigurierbar auf Agent-Ebene** (kein Regler) | Plattform-Default (Hybrid); exakte Steuerung nur über kbaas-Retrieve-API |
| Include citations | Yes | ok, aber UI kann die gelieferten Objekte nicht anzeigen (siehe 03) |
| Region | **Toronto TOR1** | Mismatch zur App (FRA); nachträglich nicht änderbar → bei Neuanlage FRA wählen |
| Visibility | Private (Zugriff via Access Keys) | richtig |
| Guardrails | Content Moderation ON · Jailbreak Detection ON · Sensitive Data Detection OFF | SDD-off ist korrekt begründet (deutsche False-Positives, z. B. „dem" als sensibel erkannt); Moderation+Jailbreak für ~$0.01/Monat behalten |
| Attached KB | rag-assistant-hh9v-kb | 1 KB, korrekt |
| Access Keys | **≥2 Seiten „chat-ui"-Keys** (30.06. 17:58 → 01.07. 09:21 auf Seite 1, weitere auf Seite 2) | Leck durch App-Startup-Minting; bereinigen |

## Instructions-Review (Volltext in Konsole eingesehen)

Stärken:
- Klare Rollen-/Sprachlogik (Deutsch default, Sprache spiegeln), gutes Antwortformat (Kurzantwort/Ursache/Selbstcheck/Empfehlung), saubere Sicherheitsliste (Strom, Kältemittel, EEV …), Fallback-Sätze für „nicht gefunden" vs. „KB nicht erreichbar", Quellen-Nennung, kein Roh-JSON.
- E999-Test bestätigt: erfindet keine unbekannten Codes ✓.

Schwächen / Korrekturbedarf:
1. „Prüfe sowohl Schreibweise mit ‚E' als auch die reine Zahl" — **wirkungslos**: Das LLM kann die Retrieval-Query nicht beeinflussen (Method: None nutzt die Roh-Nachricht). Normalisierung muss VOR dem Agent passieren (Backend) oder per deterministischem Lookup gelöst werden.
2. Die beiden Fallback-Sätze sind gut definiert, aber das Modell kann „Retrieval lieferte nichts" nicht von „Retrieval ausgefallen" unterscheiden (es sieht nur fehlenden Kontext) → sagt praktisch immer „keine gesicherten Informationen", auch bei Plattform-Timeouts. Die Unterscheidung muss das Backend über `retrieval_status` treffen und ggf. den Timeout-Satz selbst rendern.
3. Solar-Fernbedienung: Instructions behaupten „über USB-C laden" als erlaubte Antwort — im Test T10 kam eine plausible, aber quellenfremd angereicherte Antwort („2–3 h direkte Sonne", LED-Verhalten). Instructions sollten keine Fachdetails enthalten, die nicht sicher in der KB stehen (sonst Halluzinations-Anker).
4. Quellen-Naming („Quelle: Technisches Handbuch …") kollidiert mit `[[C1]]`-Citations — vereinheitlichen, sobald die UI echte Quellen rendert.

## Verhalten (Live-Belege)

- Konsole-Playground „error 465" → **korrekt** („Compressor overload error", C1-Zitat) — 25 min nachdem dieselbe Query via App scheiterte. Retrieval am Alpha-Knife-Edge + zeitweise Degradation ⇒ nicht deterministisch. Empfehlung: nicht an der Agent-Schraube drehen, sondern Codes deterministisch lösen (siehe 10).
- Invoice-Telemetrie: 19.5k Moderation- + 6.1k Jailbreak-Tokens im Juli — Guardrails aktiv und günstig.
- Beobachteter Legacy-Score `-9549511700` in Citations: taucht wörtlich als Beispielwert in der DO-Doku auf → Platzhalter/Sentinel der Plattform (kein lokaler Datenfehler); nicht als Ranking-Signal interpretieren.
