"""MIT subject evaluations -> evals extract (format only; no fetcher).

Evaluations sit behind MIT Touchstone, so they can't be fetched by the scheduled run. Once per
term a logged-in browser run extracts the hours and writes evals.json (raw reports never leave
the personal/ folder; only these extracted numbers are public).

Format 1 (what that run should write):

    {"format": 1, "source": "MIT subject evaluations", "extracted_at": "2027-01-20",
     "records": [{"number": "6.5060", "title": "Algorithm Engineering", "term": "Fall 2025",
                  "hours_in": 3.5, "hours_out": 10, "responses": 2,
                  "instructor": null, "instructor_match": true}]}

`title` is the subject title on the evaluation report. Special subjects (X.Sxxx) reuse numbers
for different topics each term, so their hours may only be attached to a course whose title
matches. The legacy file (a dict keyed by number, fields prefixed eval_) has no titles; it is
still read, and its special-subject entries are reported as untitled.
"""

import json
import os
import re

FIELDS = ("hours_in", "hours_out", "responses", "term", "instructor", "instructor_match")


def from_legacy(data):
    records = []
    for number, ev in sorted(data.items()):
        rec = {"number": number, "title": None}
        for f in FIELDS:
            rec[f] = ev.get("eval_" + f)
        rec["status"] = ev.get("eval_status")
        records.append(rec)
    return {"format": 1, "source": "MIT subject evaluations (legacy evals.json)",
            "extracted_at": None, "records": records}


def load(path):
    """Read evals.json in either format. Returns (extract, problems)."""
    if not os.path.exists(path):
        return {"format": 1, "records": []}, [("warn", "no evals.json")]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ex = data if isinstance(data, dict) and data.get("format") == 1 else from_legacy(data)
    untitled = [r["number"] for r in ex["records"]
                if re.match(r"[0-9A-Z]+\.S", r["number"]) and not r.get("title")]
    problems = []
    if untitled:
        problems.append(("info", "%d special-subject evals have no title (legacy file); "
                                 "title matching starts with the next evals run" % len(untitled)))
    return ex, problems


def legacy_fields(rec):
    """Record -> the eval_* fields data.js uses today."""
    out = {"eval_" + f: rec.get(f) for f in FIELDS}
    out["eval_status"] = rec.get("status", "ok")
    return out
