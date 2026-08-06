# 02 — Ressourcen-Inventar (read-only, Quellen: DO-Konsole via Co-Browsing + Juli-Rechnung 550730561)

Maschinenlesbar: `results/resource-inventory.json`

| Ressource | ID / Name | Region | Größe | Status | $/Monat | Zweck |
|---|---|---|---|---|---|---|
| App Platform App | rag-assistant-hh9v-chat (professional) | fra | apps-s-1vcpu-2gb ×1 | live | 25.00 | Chat-UI + FastAPI-Proxy |
| — Component | chat-ui | fra | Dockerfile, Port 8080 | live | (inkl.) | serviert index.html, /api/chat |
| GenAI Agent | rag-assistant-hh9v-agent · 44bcacc0-… | tor1 | GPT-oss-20b | live, Private | 0.04 (Juli) | RAG-Antworten |
| Knowledge Base | rag-assistant-hh9v-kb · 479333ec-… | tor1 (kbaas) | 4 Quellen, 11.58 MiB | Completed | (Tokens) | Wissensbasis |
| OpenSearch-Cluster | genai-walrus | **tor1** | Basic 2 GB/1 vCPU, 1 Node, 40 GiB | live | 19.60 | KB-Index-Storage |
| Embedding-Modell | Qwen3 Embedding 0.6B | — | $0.04/1M Tokens | aktiv | ~0.00 | Indexierung + Query-Vektorisierung |
| Foundation-Modell | OpenAI GPT-oss-20b | — | $0.05/M in · $0.45/M out | aktiv | 0.04 | Antwortgenerierung |
| Reranker | — | — | nicht konfiguriert | — | 0 | (Empfehlung: BGE Reranker v2 m3, $0.01/M) |
| Guardrails | Content Moderation + Jailbreak Detection | — | $0.20/M Tokens | on | 0.01 | Input-/Output-Prüfung |
| — | Sensitive Data Detection | — | — | **off** (deutsche False-Positives) | 0 | — |
| Agent Access Keys | „chat-ui" ×(2 Seiten, ≥10) | — | — | **Wildwuchs** | 0 | App-Authentifizierung |
| Serverless Inference | GPT-oss-20b/120b (Ad-hoc-Tests) | — | — | genutzt Juli | 0.04 | Playground/Tests |
| Domain | ondigitalocean.app-Subdomain | — | — | aktiv | 0 | öffentliche Test-URL |
| Logs/Observability | App-Platform-Logs, Agent Observability-Tab | — | — | Standard | 0 | Diagnose |

## Juli-Rechnung (Ground Truth)

```
App Platform  chat-ui 744h apps-s-1vcpu-2gb          $25.00
OpenSearch    genai-walrus Basic 2GB/1vCPU  744h     $11.00
OpenSearch    Additional Storage 40 GiB     744h      $8.60
GenAI Agent   in 206,041 tok / out 21,275 tok
              + Moderation 19,545 + Jailbreak 6,131   $0.04
Serverless    GPT-oss-20b + 120b Tests                $0.04
─────────────────────────────────────────────────────────
Nutzung $44.68 · Credits −$4.39 · zzgl. 20% USt → $48.35
```

Anmerkungen:
- Die Rechnung weist die 40 GiB als „Additional Storage" aus; laut aktueller Preisseite ist der Basic-2GB-Plan mit **40–200 GiB** Storage definiert, Listenpreis $19.60 — **40 GiB ist das Minimum**, ein Storage-Downsize unterhalb 40 GiB existiert nicht.
- Traffic Juli ≈ 60–100 Chats (aus 206k Input-Tokens ÷ ~6.9k/Anfrage) — Pilotniveau; Tokenkosten bleiben auch bei 100-fachem Traffic unter $10.
- Indexkosten real gemessen: kompletter md-Index-Lauf 10.340 Tokens = **$0.00041**.
