"""Publish the course database for the site.

    db.js       window.COURSE_DB = {meta, courses}: every course with its term offerings and
                designations (no per-field history, which stays on the data branch)
    changes.js  window.COURSE_CHANGES = {since, changes}: recent changes from the feed, which
                the planner uses for alerts ("units changed since you planned it")

The change feed itself (db/changes.jsonl on the data branch) is append-only: one line per
change, every run. The run that first creates the database writes no feed lines (everything
would be "added").
"""

import json
import os
from datetime import date, timedelta

from . import terms

FEED_PATH = os.path.join("db", "changes.jsonl")
RECENT_DAYS = 180
_COURSE_KEYS = ("id", "number", "kind", "title", "department", "category", "description", "url",
                "prereq_raw", "prereq_numbers", "meets_with", "group", "aliases",
                "range_numbers", "designations", "evals", "first_seen", "last_seen", "removed",
                "renumbered_to")
_OFFERING_KEYS = ("status", "units", "half", "instructor", "schedule_summary", "first_seen",
                  "last_seen")


def append_feed(root, changes):
    if not changes:
        return
    path = os.path.join(root, FEED_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for c in changes:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def read_feed(root):
    path = os.path.join(root, FEED_PATH)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def db_payload(db, years):
    courses, all_terms = [], set()
    for cid in sorted(db["courses"]):
        c = db["courses"][cid]
        out = {k: c[k] for k in _COURSE_KEYS if c.get(k) not in (None, [], {}, "")}
        offs = {}
        for t, o in c["offerings"].items():
            all_terms.add(t)
            off = {k: o[k] for k in _OFFERING_KEYS if o.get(k) not in (None, [], {}, "")}
            if o.get("title") and o["title"] != c["title"]:
                off["title"] = o["title"]
            offs[t] = off
        out["offerings"] = offs
        courses.append(out)
    meta = {"run_id": db.get("run_id"), "updated": db.get("updated"),
            "current_term": years.get("term"), "academic_year": years.get("this"),
            "terms": sorted(all_terms, key=terms.key), "course_count": len(courses)}
    return {"meta": meta, "courses": courses}


def changes_payload(feed, today, days=RECENT_DAYS):
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    return {"since": since, "changes": [c for c in feed if c["date"] >= since]}


def write_js(path, var, payload):
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.%s = " % var)
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
