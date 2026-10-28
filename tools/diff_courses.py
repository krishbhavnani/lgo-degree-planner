#!/usr/bin/env python3
"""Readable diff of two courses.json files (or data.js files): what a data change does to the site.

    python3 tools/diff_courses.py OLD NEW [--fields title,units_total,...] [--limit 40]

Reports courses added/removed (by number), rows that appear more than once, and per-field
changes for courses in both. Volatile fields (pulled_at, prereq name lists) are ignored.
"""

import json
import sys
from collections import Counter, defaultdict

IGNORE = {"prereqs"}


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.startswith("window.COURSE_DATA"):
        text = text[text.index("=") + 1:].strip().rstrip(";")
    return json.loads(text)


def short(v, n=70):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n - 1] + "…"


def diff(old, new, fields=None, limit=40):
    out = []
    oc, nc = old["courses"], new["courses"]
    ocount, ncount = Counter(c["number"] for c in oc), Counter(c["number"] for c in nc)
    out.append("Courses: %d -> %d" % (len(oc), len(nc)))
    for label, cnt in (("old", ocount), ("new", ncount)):
        d = sorted(n for n, k in cnt.items() if k > 1)
        if d:
            out.append("Duplicate numbers in %s: %s" % (label, ", ".join(
                "%s ×%d" % (n, cnt[n]) for n in d)))
    obn = {c["number"]: c for c in oc}
    nbn = {c["number"]: c for c in nc}
    added = sorted(set(nbn) - set(obn))
    removed = sorted(set(obn) - set(nbn))
    out.append("")
    out.append("Added (%d):" % len(added))
    out += ["  + %-14s %s" % (n, short(nbn[n].get("title", ""))) for n in added]
    out.append("Removed (%d):" % len(removed))
    out += ["  - %-14s %s" % (n, short(obn[n].get("title", ""))) for n in removed]

    changes = defaultdict(list)
    for n in sorted(set(obn) & set(nbn)):
        a, b = obn[n], nbn[n]
        for k in sorted(set(a) | set(b)):
            if k in IGNORE or (fields and k not in fields):
                continue
            if a.get(k) != b.get(k):
                changes[k].append((n, a.get(k), b.get(k)))
    out.append("")
    out.append("Field changes on courses in both:" + ("" if changes else " none"))
    for k in sorted(changes, key=lambda k: -len(changes[k])):
        rows = changes[k]
        out.append("  %s: %d course(s)" % (k, len(rows)))
        for n, a, b in rows[:limit]:
            out.append("      %-12s %s  ->  %s" % (n, short(a, 50), short(b, 50)))
        if len(rows) > limit:
            out.append("      … %d more" % (len(rows) - limit))
    om, nm = old.get("meta", {}), new.get("meta", {})
    meta_changes = [k for k in sorted(set(om) | set(nm))
                    if k != "pulled_at" and om.get(k) != nm.get(k)]
    if meta_changes:
        out.append("")
        out.append("Meta changes:")
        for k in meta_changes:
            out.append("  %s: %s  ->  %s" % (k, short(om.get(k), 60), short(nm.get(k), 60)))
    return "\n".join(out)


def main():
    argv = sys.argv[1:]
    opts, args = {}, []
    while argv:
        a = argv.pop(0)
        if a in ("--fields", "--limit") and argv:
            opts[a] = argv.pop(0)
        else:
            args.append(a)
    if len(args) != 2:
        sys.exit(__doc__)
    fields = set(opts["--fields"].split(",")) if "--fields" in opts else None
    print(diff(load(args[0]), load(args[1]), fields, int(opts.get("--limit", 40))))


if __name__ == "__main__":
    main()
