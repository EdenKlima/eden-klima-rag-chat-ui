# 08 — Sicherheits-Audit

## Kritisch

| # | Befund | Risiko | Fix |
|---|---|---|---|
| S1 | **Account-weiter `DO_API_TOKEN` als Laufzeit-Secret der öffentlichen App** (nur genutzt für Agent-Discovery + Key-Minting). | RCE/SSRF/Leak in der App ⇒ Vollzugriff auf das DO-Konto (Droplets, DNS, Billing…). | Einen Agent-Access-Key manuell erzeugen → als `AGENT_ENDPOINT` + `AGENT_ACCESS_KEY` Env-Secrets setzen → Discovery-/Minting-Code entfernen → `DO_API_TOKEN` aus der App-Spec löschen → Token im DO-Panel **rotieren** (er existierte in App-Env/Prozessspeicher). |
| S2 | **Key-Minting bei jedem Boot** ohne Cleanup: ≥2 Seiten „chat-ui"-Keys am Agent (30.06.–heute). Jeder Key ist ein gültiger Endpoint-Zugang; Inventar unkontrolliert. | Vergrößerte Angriffsfläche; kein Audit-Trail, welcher Key wo lebt. | Nach S1: alle bis auf den einen aktiven Key in der Konsole löschen. |

## Mittel

| # | Befund | Fix |
|---|---|---|
| S3 | `/api/chat` offen ohne Rate-Limit/Auth; `message`/History ohne Längenlimit → Token-Burn, Prompt-Abuse, 90-s-Slots blockierbar. | Einfaches IP-Rate-Limit (z. B. slowapi, 10/min), `message` ≤ 2.000 Zeichen, History serverseitig auf letzte N=8 Turns kappen. |
| S4 | Client-kontrollierte `role`-Felder werden 1:1 durchgereicht (auch `system`). | Whitelist `user`/`assistant`, alles andere verwerfen. |
| S5 | Kein `.dockerignore`: `.git/` + `blueprints/` landen im Image. | `.dockerignore` mit `.git`, `blueprints`, `docs`, `README.md`. |

## Niedrig / positiv

- ✓ XSS: Frontend escapet vor dem Rendern; keine `dangerouslySetInnerHTML`-Äquivalente.
- ✓ Keine Secrets in Logs; Fehlermeldungen an Nutzer generisch.
- ✓ Agent Private + Access-Key-Auth (statt public endpoint).
- ✓ Sensitive-Data-Guardrail off ist dokumentiert begründet (deutsche False-Positives — „dem" wurde als sensibel geblockt); Moderation + Jailbreak bleiben on.
- ⚠ `/health` exponiert `agent_error`-Interna (Discovery-Fehlertexte) — auf boolean reduzieren.
- ⚠ Statuspage-Gate (B8): externer Dienst entscheidet über Verfügbarkeit der eigenen App; bewusst lassen oder auf Banner statt Hard-Block umbauen.
- ℹ Repo privat halten (enthält jetzt Audit-Interna); keine Tokens im Repo gefunden ✓.

## Empfohlene Ziel-Env der App

```
AGENT_ENDPOINT   = https://iuahhjpgd4wy64ndnf7hormx.agents.do-ai.run/api/v1/chat/completions
AGENT_ACCESS_KEY = <ein dedizierter Key, Rotation halbjährlich>
AGENT_NAME       = Eden Klima Wissensassistent
# DO_API_TOKEN entfällt ersatzlos
```
