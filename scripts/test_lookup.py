#!/usr/bin/env python3
"""Offline tests for the deterministic error-code path in main.py (no network).

Run from the repo root with fastapi+httpx installed:
    python3 scripts/test_lookup.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name} {detail}")


def intent(msg):
    return main.detect_error_code_intent(msg)


def codes_of(res):
    if not res or res["type"] != "codes":
        return []
    return [r["code"] for r in res["records"]]


# --- positive detections -----------------------------------------------------
check("bare code", codes_of(intent("465")) == ["465"])
check("bare e-code lower", codes_of(intent("e465")) == ["465"])
check("E dash code", codes_of(intent("Fehler E-554")) == ["554"])
check("error prefix", codes_of(intent("error 464")) == ["464"])
check("typo eror", codes_of(intent("eror 465")) == ["465"])
check("german question", codes_of(intent("Was bedeutet Fehler 464?")) == ["464"])
check("zeigt phrasing", codes_of(intent("Warum zeigt meine Klimaanlage 554?")) == ["554"])
check("model number + code", codes_of(intent("Mein AR12TXFCAWKNEU zeigt E101")) == ["101"])
check("windfree phrase", codes_of(intent("Windfree AR9500 Fehler 554")) == ["554"])
check("two codes", codes_of(intent("Was bedeuten Fehler 464 und 465?")) == ["464", "465"])

# --- negatives ---------------------------------------------------------------
check("no false positive volts", intent("Die Anlage läuft mit 230 V Netzspannung, was tun?") is None)
check("no false positive year", intent("Wartungsvertrag seit 2026 kündigen?") is None)
check("no false positive R410A", intent("Kann ich R410A selbst nachfüllen?") is None)
check("plain question", intent("Wie oft sollte eine Klimaanlage gewartet werden?") is None)
check("solar question", intent("Wie lade ich die Samsung Solar-Fernbedienung?") is None)

# --- missing + range coverage ------------------------------------------------
res = intent("Was bedeutet der Fehler E999?")
check("unknown code detected", res is not None and res["type"] == "codes" and res["missing"] == ["999"], str(res))
check("unknown code has no verified data", not main.lookup_has_verified_data(res))
block = main.build_dataset_block(res)
check("unknown code block honest", "NICHT" in block and "999" in block)

res = intent("Fehler 113")
check("range covering 113", res is not None and res["range_records"] and res["range_records"][0]["key"] == "101~120", str(res))

res = intent("101~120 was bedeutet dieser Bereich?")
check("explicit range entry", res is not None and res["type"] == "codes" and res["range_records"], str(res))

# --- aggregation intents -----------------------------------------------------
res = intent("Welche Fehlercodes kennst du?")
check("list all", res is not None and res["type"] == "list_all", str(res))
check("list all block has total", "446" in (main.build_dataset_block(res) or ""))

res = intent("Welche Fehlercodes gibt es zwischen 460 und 470?")
check("list range", res is not None and res["type"] == "list_range" and res["from"] == 460 and res["to"] == 470, str(res))
block = main.build_dataset_block(res)
check("range block contains 464..470", all(c in block for c in ("464", "465", "466", "470")))

res = intent("Welche Fehlercodes gelten für DVM?")
check("list group", res is not None and res["type"] == "list_group" and res["group"] == "DVM", str(res))
check("group block mentions DVM count", "DVM" in (main.build_dataset_block(res) or ""))

res = intent("Wie viele Fehlercodes sind dokumentiert?")
check("how many", res is not None and res["type"] == "list_all", str(res))

# --- record content ----------------------------------------------------------
res = intent("error 465")
block = main.build_dataset_block(res)
check("465 block message", "Compressor overload error" in block)
check("465 block groups", "FJM, CAC, DVM, EHS" in block)
check("465 block e-code", "E465" in block)

# --- neighbors ---------------------------------------------------------------
neighbors = main._neighbor_codes("544")
check("neighbors near 544", "554" in neighbors or "545" in neighbors, str(neighbors))

# --- content cleaning --------------------------------------------------------
check("citation strip", main._clean_content("Antwort [[C1]] und [C2] Ende.") == "Antwort und Ende.")
check("markdown link untouched", main._clean_content("Siehe [Doku](https://x) fertig.") == "Siehe [Doku](https://x) fertig.")

# --- guardrail canned-text detection -----------------------------------------
canned = "I'm not able to respond to that request, but I can answer other questions."
check("canned marker matches", any(m in canned for m in main.GUARDRAIL_CANNED_MARKERS))
check("german answer untouched by markers", not any(m in "Dazu liegen mir keine Informationen vor." for m in main.GUARDRAIL_CANNED_MARKERS))
check("safe message mentions technician", "Fachtechniker" in main.GUARDRAIL_SAFE_MESSAGE and "Eden Klima" in main.GUARDRAIL_SAFE_MESSAGE)

# --- sources extraction ------------------------------------------------------
data = {
    "retrieval": {
        "retrieved_data": [
            {"filename": "a.pdf", "page_number": 18, "score": -9549511700.0},
            {"filename": "a.pdf", "page_number": 18, "score": 0.5},
            {"filename": "b.md", "metadata": {"page_number": 2}, "score": 0.91},
        ]
    }
}
sources, status = main._extract_sources(data, lookup_used=False)
check("sources status success", status == "success")
check("sources deduped", [s["filename"] for s in sources] == ["a.pdf", "b.md"], str(sources))
check("sentinel score dropped", sources[0]["score"] is None)
check("real score kept", sources[1]["score"] == 0.91)

sources, status = main._extract_sources({"retrieval": {"retrieved_data": []}}, lookup_used=True)
check("lookup source injected", sources and sources[0]["filename"] == main.ERROR_CODES_SOURCE_LABEL)
check("empty retrieval status", status == "empty")

sources, status = main._extract_sources({"citations": [{"id": "x"}]}, lookup_used=False)
check("no retrieval field -> unknown", status == "unknown" and sources == [])

# --- streaming chunk handling ------------------------------------------------
emit, keep = main.split_streamable("Antwort [[C1")
check("partial marker held back", (emit, keep) == ("Antwort", " [[C1"), f"{emit!r} {keep!r}")
emit2, keep2 = main.split_streamable(keep + "]] Ende")
check("marker removed across chunks", (emit2.strip(), keep2) == ("Ende", ""), f"{emit2!r} {keep2!r}")
emit3, keep3 = main.split_streamable("Siehe [Doku](https://x)")
check("markdown link not held back", (emit3, keep3) == ("Siehe [Doku](https://x)", ""), f"{emit3!r} {keep3!r}")
emit4, keep4 = main.split_streamable("Text ohne Marker")
check("plain text passes through", (emit4, keep4) == ("Text ohne Marker", ""))
emit5, keep5 = main.split_streamable("Wort ")
check("trailing space held back", (emit5, keep5) == ("Wort", " "), f"{emit5!r} {keep5!r}")

# no double space where a marker was removed across chunk boundaries
chunks, out, buf = ["d er", "ror ", "[[C1", "]] l", "aut."], "", ""
for c in chunks:
    buf += c
    emitted, buf = main.split_streamable(buf)
    out += emitted
out += main.CITATION_MARKER_RE.sub("", buf)
check("no double space after marker", out == "d error laut.", repr(out))

delta, payload = main._parse_stream_chunk('{"choices":[{"delta":{"content":"Hallo"}}]}')
check("delta parsed", delta == "Hallo" and payload is not None)
check("done sentinel ignored", main._parse_stream_chunk("[DONE]") == ("", None))
check("garbage line ignored", main._parse_stream_chunk("not json") == ("", None))
delta5, payload5 = main._parse_stream_chunk('{"retrieval":{"retrieved_data":[]},"choices":[]}')
check("retrieval chunk keeps payload", delta5 == "" and payload5.get("retrieval") is not None)

# --- guardrail replacement helper --------------------------------------------
c, s, g = main._apply_guardrail_replacement("I'm not able to respond to that request.", [{"filename": "x"}], [])
check("guardrail replaced", c == main.GUARDRAIL_SAFE_MESSAGE and s == [] and "content_moderation" in g)
c2, s2, g2 = main._apply_guardrail_replacement("Normale Antwort", [{"filename": "x"}], [])
check("normal answer untouched", c2 == "Normale Antwort" and len(s2) == 1 and g2 == [])

# --- rate limiting -----------------------------------------------------------
main._RATE_BUCKETS.clear()
limit = main.RATE_LIMIT_PER_MINUTE
allowed = sum(0 if main.rate_limited("test-ip", now=1000.0 + i * 0.01) else 1 for i in range(limit + 5))
check("rate limit caps burst", allowed == limit, f"allowed={allowed} limit={limit}")
check("window slides", not main.rate_limited("test-ip", now=1000.0 + 120), "still limited after 2 min")
main._RATE_BUCKETS.clear()

# --- history sanitizing ------------------------------------------------------
hist = main._sanitize_history(
    [{"role": "system", "content": "evil"}] + [{"role": "user", "content": f"m{i}"} for i in range(30)]
)
check("history cap", len(hist) == main.MAX_HISTORY_ENTRIES, str(len(hist)))
check("system role dropped", all(h["role"] in ("user", "assistant") for h in hist))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
