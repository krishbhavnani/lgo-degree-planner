"""Course database: courses x offerings, kept across runs on the data branch (db/courses.json).

    course   one per identity (see identity.py): number, title, department, description,
             joint group, meets-with links, aliases, designations (AAGS, design, Action
             Learning, each with source and scope), evaluation hours, first/last seen, history
    offering one per course per term: status, title, units, half term, instructor, schedule
             (current term only), first/last seen, history

Offering status
    listed       in this academic year's catalog for that term
    not_offered  the catalog says "Not offered academic year ..."
    expected     next academic year; regularly offered in that season and not flagged
    unverified   next academic year with no basis (special subjects, "not offered regularly",
                 "not currently listed"), or this year when the catalog lists no schedule icon
    removed      was listed, then disappeared (never deleted; keeps last_seen)

Each run: observe() turns this run's parsed sources into a fresh view; merge() folds it into
the stored database and returns the list of changes. Past terms are frozen: only the current
term and later are updated or marked removed.
"""

import copy
import json
import os
import re

from . import identity, terms

FORMAT = 1
DB_PATH = os.path.join("db", "courses.json")

COURSE_FIELDS = ("number", "kind", "title", "department", "category", "description", "url",
                 "prereq_raw", "prereq_numbers", "meets_with", "same_as", "group",
                 "range_numbers", "designations", "evals")
OFFERING_FIELDS = ("status", "title", "units", "half", "instructor", "schedule_summary",
                   "schedule", "date_note", "source")
_NOT_LOGGED = {"schedule"}   # schedule_summary carries the readable change


def empty():
    return {"format": FORMAT, "run_id": None, "updated": None, "courses": {},
            "renumber_candidates": []}


def load(root):
    path = os.path.join(root, DB_PATH)
    if not os.path.exists(path):
        return empty()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(root, db):
    path = os.path.join(root, DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = dict(db, courses={k: db["courses"][k] for k in sorted(db["courses"])})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ---------------------------------------------------------------------------
# Observe: this run's view
# ---------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def half_from_date_note(note, season):
    """'Ends Oct 23' in Fall -> H1; 'Begins Nov 2' -> H2 (current term only)."""
    m = re.match(r"(Begins|Ends) ([A-Z][a-z]{2}) (\d{1,2})", note or "")
    if not m or m.group(2) not in _MONTHS:
        return None
    md = (_MONTHS[m.group(2)], int(m.group(3)))
    mid = {"Fall": (10, 24), "Spring": (3, 22)}.get(season)
    if not mid:
        return None
    if m.group(1) == "Ends" and md <= (mid[0], mid[1] + 7):
        return "H1"
    if m.group(1) == "Begins" and md >= (mid[0], mid[1] - 10):
        return "H2"
    return None


def _units(row):
    u = row.get("units") or {}
    return {"raw": row.get("units_raw"), "lec": u.get("lec"), "lab": u.get("lab"),
            "prep": u.get("prep"), "total": row.get("units_total"),
            "kind": row.get("units_kind") or ("fixed" if row.get("units_raw") else None)}


def _statuses(row, special):
    """(status for this academic year, status for next) from the catalog offering status."""
    st = row.get("offering_status") or "Offered"
    notes = " ".join(row.get("offering_notes") or [])
    this = "not_offered" if st.startswith("Not offered this year") else (
        "unverified" if st.startswith("Not currently listed") else "listed")
    if st.startswith("Not offered next year"):
        nxt = "not_offered"
    elif special or "Not offered regularly" in notes or this == "unverified":
        nxt = "unverified"
    else:
        nxt = "expected"
    return this, nxt


def _lab_seasons(row):
    """Seasons the booklet gives for a lab: 'Fall+IAP' -> ['Fall', 'IAP']."""
    return [p.strip().title() if p.strip().upper() != "IAP" else "IAP"
            for p in re.split(r"[+&]", row.get("al_term") or "") if p.strip()]


def _lab_matches_row(row):
    """A special-subject lab is this catalog row only if the booklet's terms are the row's."""
    seasons = _lab_seasons(row)
    return bool(seasons) and set(seasons) <= set(row.get("terms") or [])


def _topic(row, eecs_titles):
    """Title that identifies a special subject's topic."""
    n = row["number"]
    if n in eecs_titles:
        return eecs_titles[n]
    if row.get("action_learning") and row.get("al_name") and _lab_matches_row(row):
        return row["al_name"]
    return _catalog_title(row)


def _catalog_title(row):
    """The catalog's own title (undo the published '<lab name> (<code>)' retitling)."""
    t = identity.clean_title(row.get("title"))
    if row.get("action_learning") and row.get("al_name"):
        t = re.sub(r"\s*\(%s\)$" % re.escape(row["action_learning"]), "", t)
        if t == row["al_name"] and row.get("catalog_title"):
            t = row["catalog_title"]
    return t


def observe(ctx):
    """ctx (from scrape.build): rows (published course rows), special (EECS subject-update
    records), eval_records (by number), design_rows, years. Returns {id: course view}."""
    years = ctx["years"]
    this_ay, current = years["this"], years["term"]
    next_ay = terms.next_ay(this_ay)
    special_by_num = {}
    for rec in ctx["special"]:
        for n in rec["numbers"]:
            special_by_num.setdefault(n, rec)
    eecs_titles = {n: r["title"] for n, r in special_by_num.items()}
    out = {}
    for row in ctx["rows"]:
        n = row["number"]
        special = identity.is_special(n) and not identity.is_range(n)
        topic = _topic(row, eecs_titles) if special else identity.clean_title(row.get("title"))
        cid = identity.course_id(n, topic)
        kind = "range" if identity.is_range(n) else ("special" if special else "regular")
        same_as = row.get("same_as") or []
        lab_elsewhere = special and row.get("action_learning") and not _lab_matches_row(row)
        course = {
            "id": cid, "number": n, "kind": kind, "title": topic,
            "department": row.get("department"), "category": row.get("category"),
            "description": row.get("description") or "", "url": row.get("url"),
            "prereq_raw": row.get("prereq_raw") or "",
            "prereq_numbers": row.get("prereq_numbers") or [],
            "meets_with": row.get("meets_with") or [], "same_as": same_as,
            "group": "+".join(sorted(set([n] + same_as))) if same_as else None,
            "range_numbers": row.get("range_numbers"),
            "designations": _designations(row, special, topic, ctx, this_ay,
                                          lab=not lab_elsewhere),
            "evals": _evals(row, special, topic, ctx),
            "aliases": [],
            "offerings": {},
        }
        rec = special_by_num.get(n) if row.get("is_special") else None
        if rec:   # EECS subject-update course: one listed offering in the term it names
            course["aliases"] = list(rec.get("was") or [])
            course["offerings"][rec["term"]] = {
                "status": "listed", "title": topic, "units": _units(row),
                "half": None, "instructor": row.get("instructor"),
                "schedule_summary": row.get("schedule_summary") if rec["term"] == current else None,
                "schedule": None, "date_note": None}
        else:
            this, nxt = _statuses(row, special)
            for season in row.get("terms") or []:
                for ay, status in ((this_ay, this), (next_ay, nxt)):
                    t = terms.term(season, ay)
                    if terms.key(t) < terms.key(current):
                        continue   # e.g. Summer of this AY when the current term is Fall
                    off = {"status": status, "title": topic, "units": _units(row),
                           "half": row.get("half_term"),
                           "instructor": row.get("instructor") if ay == this_ay else None,
                           "schedule_summary": None, "schedule": None, "date_note": None}
                    if t == current:
                        off["schedule_summary"] = row.get("schedule_summary") or None
                        off["schedule"] = row.get("schedule") or None
                        off["date_note"] = row.get("date_note")
                        off["half"] = off["half"] or half_from_date_note(off["date_note"], season)
                    course["offerings"][t] = off
        for rec2 in (special_by_num.get(x) for x in [n]):
            if rec2 and not rec:   # EECS "(was X)" notes also apply to catalog rows
                course["aliases"] = list(rec2.get("was") or [])
        if cid not in out:
            out[cid] = course
        if lab_elsewhere:
            lab = _lab_course(row, this_ay, current, ctx)
            out.setdefault(lab["id"], lab)
    return out


def _lab_course(row, this_ay, current, ctx):
    """A special-subject lab the booklet places in a term the catalog row doesn't run in
    (15.S04 is a Fall seminar in the catalog; the booklet's Generative AI Lab is Spring)."""
    name = row["al_name"]
    course = {
        "id": identity.course_id(row["number"], name), "number": row["number"],
        "kind": "special", "title": name, "department": row.get("department"),
        "category": row.get("category"), "description": "", "url": None, "prereq_raw": "",
        "prereq_numbers": [], "meets_with": [], "same_as": [], "group": None,
        "range_numbers": None,
        "designations": _designations(row, True, name, ctx, this_ay, lab=True, aags=False,
                                      design=False),
        "evals": None, "aliases": [], "offerings": {}}
    for season in _lab_seasons(row):
        t = terms.term(season, this_ay)
        if terms.key(t) >= terms.key(current):
            course["offerings"][t] = {"status": "listed", "title": name,
                                      "units": {"raw": None, "lec": None, "lab": None,
                                                "prep": None, "total": None, "kind": None},
                                      "half": None, "instructor": None,
                                      "schedule_summary": None, "schedule": None,
                                      "date_note": None, "source": "booklet"}
    return course


def _designations(row, special, topic, ctx, this_ay, lab=True, aags=True, design=True):
    d = {}
    if aags and row.get("aags") and row["aags"].startswith("Approved"):
        d["aags"] = {"value": row["aags"], "source": "EECS AAGS list", "scope": this_ay}
    dz = row.get("design_approved") if design else None
    if dz and special:
        # Special-subject numbers are reused: the design list must name this topic.
        ok = any(row["number"] in r.get("numbers", []) and
                 identity.titles_match(r.get("name"), topic) for r in ctx["design_rows"])
        dz = dz if ok else None
    if dz:
        d["design"] = {"value": dz, "source": "LGO handbook, Appendix 2"}
    if lab and row.get("action_learning"):
        d["action_learning"] = {"code": row["action_learning"], "name": row.get("al_name"),
                                "term": row.get("al_term"),
                                "status": row.get("al_status", "confirmed"),
                                "source": "MIT Sloan Action Learning booklet",
                                "scope": this_ay}
    return d


def _evals(row, special, topic, ctx):
    rec = ctx["eval_records"].get(row["number"])
    if not rec or (rec.get("hours_in") is None and rec.get("hours_out") is None):
        return None
    if special and not identity.titles_match(rec.get("title"), topic):
        return None   # can't verify the evaluation is for this topic
    return {k: rec.get(k) for k in ("hours_in", "hours_out", "responses", "term", "instructor",
                                    "instructor_match")}


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
def _change(changes, date, run_id, course, kind, term=None, field=None, old=None, new=None):
    c = {"date": date, "run_id": run_id, "id": course["id"], "number": course["number"],
         "kind": kind}
    if term:
        c["term"] = term
    if field:
        c.update(field=field, old=old, new=new)
    changes.append(c)


def merge(db, observed, run_id, date, current_term, aliases=()):
    """Fold this run's observed courses into db (in place). Returns the list of changes."""
    changes = []
    courses = db["courses"]
    added_ids, removed_ids = [], []

    for cid, obs in observed.items():
        c = courses.get(cid)
        if c is None:
            c = {k: copy.deepcopy(obs[k]) for k in ("id",) + COURSE_FIELDS}
            c.update(aliases=list(obs["aliases"]), first_seen=date, last_seen=date,
                     history=[], offerings={})
            courses[cid] = c
            added_ids.append(cid)
            _change(changes, date, run_id, c, "course_added")
        else:
            if c.get("removed"):
                _change(changes, date, run_id, c, "course_returned", old=c["removed"])
                del c["removed"]
            for f in COURSE_FIELDS:
                if c.get(f) != obs.get(f):
                    if f not in ("prereq_numbers",):
                        c["history"].append({"date": date, "field": f, "old": c.get(f),
                                             "new": obs.get(f)})
                        _change(changes, date, run_id, c, "changed", field=f, old=c.get(f),
                                new=obs.get(f))
                    c[f] = copy.deepcopy(obs.get(f))
            for a in obs["aliases"]:
                if a not in c["aliases"]:
                    c["aliases"].append(a)
            c["last_seen"] = date
        _merge_offerings(c, obs["offerings"], changes, run_id, date, current_term)

    for cid, c in courses.items():
        if cid in observed or c.get("removed"):
            continue
        c["removed"] = date
        removed_ids.append(cid)
        _change(changes, date, run_id, c, "course_removed")
        for t, off in c["offerings"].items():
            if terms.key(t) >= terms.key(current_term) and off["status"] != "removed":
                _set(off, "status", "removed", changes, run_id, date, c, t)

    _apply_aliases(db, aliases, observed)
    cands = identity.renumber_candidates([courses[i] for i in removed_ids],
                                         [courses[i] for i in added_ids])
    known = {(x["old"], x["new"]) for x in db.get("renumber_candidates", [])}
    for cand in cands:
        if (cand["old"], cand["new"]) not in known:
            cand["flagged"] = date
            db.setdefault("renumber_candidates", []).append(cand)
    db["run_id"], db["updated"] = run_id, date
    return changes


def _set(off, field, value, changes, run_id, date, course, term):
    old = off.get(field)
    off[field] = copy.deepcopy(value)
    if field not in _NOT_LOGGED:
        off.setdefault("history", []).append({"date": date, "field": field, "old": old,
                                              "new": value})
        _change(changes, date, run_id, course, "changed", term=term, field=field, old=old,
                new=value)


def _merge_offerings(c, observed, changes, run_id, date, current_term):
    offs = c["offerings"]
    for t, obs in observed.items():
        off = offs.get(t)
        if off is None:
            off = {k: copy.deepcopy(obs.get(k)) for k in OFFERING_FIELDS}
            off.update(first_seen=date, last_seen=date, history=[])
            offs[t] = off
            _change(changes, date, run_id, c, "offering_added", term=t, new=obs["status"])
            continue
        for f in OFFERING_FIELDS:
            if off.get(f) != obs.get(f):
                _set(off, f, obs.get(f), changes, run_id, date, c, t)
        off["last_seen"] = date
    for t, off in offs.items():
        if t in observed or terms.key(t) < terms.key(current_term):
            continue   # past terms are frozen
        if off["status"] != "removed":
            _set(off, "status", "removed", changes, run_id, date, c, t)


def _apply_aliases(db, aliases, observed):
    """Confirmed renumberings (aliases.json): the new course lists the old number; the old
    course points at the new one."""
    courses = db["courses"]
    by_number = {}
    for cid, c in courses.items():
        by_number.setdefault(c["number"], []).append(cid)
    for a in aliases:
        for new_id in by_number.get(a["new"], []):
            if a["old"] not in courses[new_id]["aliases"]:
                courses[new_id]["aliases"].append(a["old"])
        for old_id in by_number.get(a["old"], []):
            if old_id not in observed:
                courses[old_id]["renumbered_to"] = a["new"]
    confirmed = {(a["old"], a["new"]) for a in aliases}
    db["renumber_candidates"] = [
        x for x in db.get("renumber_candidates", [])
        if (courses.get(x["old"], {}).get("number"), courses.get(x["new"], {}).get("number"))
        not in confirmed]
