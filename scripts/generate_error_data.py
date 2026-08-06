#!/usr/bin/env python3
"""Generate the lean KB markdown and the lookup JSON from the master error-code file.

Single source of truth: data/samsung_error_codes_master.md
Outputs:
  data/samsung_air_conditioner_error_codes.md  (lean, per-code sections, E-code in title — for the knowledge base)
  data/error_codes.json                        (lookup database for the deterministic path in main.py)

Run from the repo root:  python3 scripts/generate_error_data.py
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MASTER = REPO / "data" / "samsung_error_codes_master.md"
OUT_MD = REPO / "data" / "samsung_air_conditioner_error_codes.md"
OUT_JSON = REPO / "data" / "error_codes.json"

NO_NOTE_VALUES = {"", "-", "—", "note", "keine zusätzliche notiz in der quelle."}
KNOWN_GROUPS = ("FJM", "CAC", "DVM", "ERV", "EHS")

FIELD_RE = re.compile(r"\*\*(Code|Error Message|Note|Applicable Product Group / Models)\*\*\s*\n+(.*?)(?=\n\s*\n\*\*|\Z)", re.S)
HEAD_RANGE_RE = re.compile(r"^(\d{3})\s*~\s*(\d{3})\s*[—–-]\s*(.*)$")
HEAD_CODE_RE = re.compile(r"^(\d{3})\s*[—–-]\s*(.*)$")


def parse_sections(text):
    parts = re.split(r"(?m)^## ", text)
    for raw in parts[1:]:
        heading, _, body = raw.partition("\n")
        fields = {}
        for label, value in FIELD_RE.findall(body):
            fields[label] = re.sub(r"\s+", " ", value).strip()
        yield heading.strip(), fields


def clean_note(value):
    if value is None or value.strip().lower() in NO_NOTE_VALUES:
        return None
    return value.strip()


def split_groups(raw):
    if not raw:
        return []
    tokens = [t.strip().upper() for t in raw.split(",")]
    return [t for t in tokens if t in KNOWN_GROUPS]


def main():
    text = MASTER.read_text(encoding="utf-8")
    codes = {}
    ranges = []
    order = []

    for heading, fields in parse_sections(text):
        message = fields.get("Error Message", "").strip()
        note = clean_note(fields.get("Note"))
        groups_raw = fields.get("Applicable Product Group / Models", "").strip()
        m_range = HEAD_RANGE_RE.match(heading)
        m_code = HEAD_CODE_RE.match(heading)
        if m_range:
            lo, hi = int(m_range.group(1)), int(m_range.group(2))
            entry = {
                "key": f"{lo}~{hi}", "from": lo, "to": hi,
                "message": message or m_range.group(3).strip(),
                "note": note, "groups_raw": groups_raw, "groups": split_groups(groups_raw),
            }
            ranges.append(entry)
            order.append(("range", entry))
        elif m_code:
            code = m_code.group(1)
            if code in codes:
                print(f"WARN duplicate code {code}, keeping first", file=sys.stderr)
                continue
            entry = {
                "code": code, "e_code": f"E{code}",
                "message": message or m_code.group(2).strip(),
                "note": note, "groups_raw": groups_raw, "groups": split_groups(groups_raw),
            }
            codes[code] = entry
            order.append(("code", entry))
        else:
            print(f"WARN unparsed heading: {heading!r}", file=sys.stderr)

    # --- lean markdown for the knowledge base ---
    lines = [
        "# Samsung Klimaanlagen — Fehlercode-Referenz (Eden Klima)",
        "",
        f"Referenzliste der Samsung-Fehlercodes ({len(codes)} Codes, Bereich {min(map(int, codes))}–{max(map(int, codes))}) "
        "für die Produktgruppen FJM, CAC, DVM, ERV und EHS. "
        "Jeder Fehlercode gilt in beiden Schreibweisen: mit und ohne E (Beispiel: 465 = E465 = e465).",
        "",
    ]
    for kind, e in order:
        if kind == "range":
            lo, hi = e["from"], e["to"]
            lines += [
                f"## {e['key']} (E{lo}–E{hi}) — {e['message']}",
                "",
                f"- Fehlercode-Bereich: {e['key']} (E{lo} bis E{hi})",
                f"- Fehlermeldung: {e['message']}",
                f"- Produktgruppen: {e['groups_raw'] or '—'}",
            ]
        else:
            lines += [
                f"## {e['code']} ({e['e_code']}) — {e['message']}",
                "",
                f"- Fehlercode: {e['code']} (auch {e['e_code']})",
                f"- Fehlermeldung: {e['message']}",
                f"- Produktgruppen: {e['groups_raw'] or '—'}",
            ]
        if e["note"]:
            lines.append(f"- Hinweis: {e['note']}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "source": "data/samsung_error_codes_master.md",
        "total_codes": len(codes),
        "codes": codes,
        "ranges": ranges,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    sizes = (OUT_MD.stat().st_size, OUT_JSON.stat().st_size)
    print(f"codes: {len(codes)}  ranges: {len(ranges)}")
    print(f"md:   {OUT_MD}  ({sizes[0]:,} bytes)")
    print(f"json: {OUT_JSON}  ({sizes[1]:,} bytes)")


if __name__ == "__main__":
    main()
