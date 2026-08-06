#!/usr/bin/env python3
"""Evaluation/regression runner for the Eden Klima Wissensassistent.

Sends every case from scripts/eval_cases.json to the app's /api/chat and checks
the answer against simple substring expectations. Run before and after every
deploy; deterministic cases (expect_status == "lookup") must be 100% green.

Usage:
    python3 scripts/eval.py --base-url https://rag-assistant-hh9v-chat-wlm7q.ondigitalocean.app \
        --out docs/audit/results/eval-$(date +%F).csv

Default checks per case: every must_all substring present, at least one
must_any substring present (if given), no must_not substring present,
optional expect_status match. All matching is lowercase substring matching.
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CASES = REPO / "scripts" / "eval_cases.json"


def run_case(base_url, case, timeout=110):
    payload = json.dumps({"message": case["input"], "history": []}).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    latency_ms = int((time.time() - t0) * 1000)
    return data, latency_ms


def judge(case, data):
    content = (data.get("content") or data.get("error") or "").lower()
    problems = []
    for needle in case.get("must_all", []):
        if needle.lower() not in content:
            problems.append(f"missing(all):{needle}")
    must_any = case.get("must_any", [])
    if must_any and not any(n.lower() in content for n in must_any):
        problems.append("missing(any):" + "|".join(must_any))
    for needle in case.get("must_not", []):
        if needle.lower() in content:
            problems.append(f"forbidden:{needle}")
    expect_status = case.get("expect_status")
    if expect_status and data.get("retrieval_status") != expect_status:
        problems.append(f"status:{data.get('retrieval_status')}!={expect_status}")
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--out", default="")
    parser.add_argument("--sleep", type=float, default=1.2)
    parser.add_argument("--only", default="", help="comma-separated case ids")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    rows = []
    passed = failed = skipped = 0
    for case in cases:
        if case.get("skip"):
            skipped += 1
            rows.append({"id": case["id"], "input": case["input"], "verdict": "SKIP",
                         "problems": case.get("note", ""), "retrieval_status": "", "latency_ms": "",
                         "sources": "", "content_head": ""})
            print(f"SKIP {case['id']}  {case['input'][:60]}")
            continue
        try:
            data, latency_ms = run_case(args.base_url, case)
        except Exception as exc:
            failed += 1
            rows.append({"id": case["id"], "input": case["input"], "verdict": "ERROR",
                         "problems": str(exc)[:200], "retrieval_status": "", "latency_ms": "",
                         "sources": "", "content_head": ""})
            print(f"ERROR {case['id']}  {exc}")
            continue
        problems = judge(case, data)
        verdict = "PASS" if not problems else "FAIL"
        passed += verdict == "PASS"
        failed += verdict == "FAIL"
        sources = data.get("sources") or []
        rows.append({
            "id": case["id"], "input": case["input"], "verdict": verdict,
            "problems": "; ".join(problems),
            "retrieval_status": data.get("retrieval_status", ""),
            "latency_ms": data.get("latency_ms", latency_ms),
            "sources": "; ".join(str(s.get("filename", s)) for s in sources if s) if isinstance(sources, list) else "",
            "content_head": (data.get("content") or data.get("error") or "")[:160].replace("\n", " "),
        })
        print(f"{verdict} {case['id']}  [{data.get('retrieval_status','-')}] {case['input'][:50]!r}"
              + (f"  → {problems}" if problems else ""))
        time.sleep(args.sleep)

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(cases)}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"report: {out}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
