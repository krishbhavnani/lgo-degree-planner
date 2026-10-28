#!/usr/bin/env python3
"""
Builds the LGO Degree Planner course data (data.js / courses.json).

Pipeline (see pipeline/):
  1. collect   fetch every registered source politely (or read the .scratch/ cache)
  2. extract   each source module in pipeline/sources/ parses its pages into an extract:
               catalog + AAGS (primary: any failure blocks publishing), and the secondary
               sources catalog index, EECS subject updates, LGO design list, Action Learning
               booklet (a failure keeps that source's last good extract, exit 2)
  3. check     guardrails; any failure -> nothing written, exit 1
  4. archive   with --refresh: raw pages saved change-only, gzipped, into .data/ (a worktree of
               the public `data` branch), plus extracts/ written from passing runs. Never
               committed by this script.
  5. publish   data.js / courses.json, built from the extracts plus evals.json (subject
               evaluation hours, refreshed once per term by a logged-in browser run).

Personal ratings are never merged into data.js (it is public); they load at runtime from the
gitignored personal/ratings.js overlay.

Exit codes: 0 all checks passed; 2 published with warnings; 1 failed, nothing written.

Run:  python3 scrape.py              # parse cached pages in .scratch/ (fetches any missing)
      python3 scrape.py --refresh    # fetch live from MIT, check, archive, publish
      python3 scrape.py --refresh --archive-dir PATH   # archive somewhere else
      python3 scrape.py --refresh --no-archive
"""

import json
import os
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone

from pipeline import config as pconfig
from pipeline import extracts, guardrails, snapshots
from pipeline.fetch import Fetcher, FetchResult
from pipeline.sources import (aags, action_learning, catalog, catalog_index, design,
                              eecs_updates, evals)
from pipeline.sources.common import dedupe

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".scratch")


def _from_cache(source):
    path = os.path.join(CACHE, source.cache_name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        body = f.read()
    when = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    return FetchResult(source.url, 200, body, via="cache", fetched_at=when)


def _save_cache(source, result):
    if result.ok and result.body:
        os.makedirs(CACHE, exist_ok=True)
        with open(os.path.join(CACHE, source.cache_name), "wb") as f:
            f.write(result.body)


def _get(source, refresh, fetcher, results):
    res = None if refresh else _from_cache(source)
    if res is None:
        res = fetcher.get(source.url)
    results[source.key] = res
    print("  %-30s %s  %5.0f KB%s" % (source.key, res.status, len(res.body) / 1024,
                                      "  (%s)" % res.error if res.error else ""))
    return res


def collect(sources, refresh, fetcher=None):
    """Fetch every source (live with --refresh, else from .scratch/ cache when present), then
    follow discovered links (EECS semester pages and fragments, the Action Learning booklet).

    Returns (all sources including discovered ones, results by source key). Fetched pages are
    not written to the .scratch/ cache here; main() does that only after the guardrails pass.

    Live catalog pages whose Produced stamp differs from the newest one are refetched once
    (MIT regenerates the listing daily; a fetch can straddle the regeneration).
    """
    fetcher = fetcher or Fetcher()
    results = {}
    for s in sources:
        _get(s, refresh, fetcher, results)
    if refresh:
        stamps = {}
        for s in sources:
            if s.kind == "catalog" and results[s.key].ok:
                raw, dt = snapshots.produced_stamp(results[s.key].text())
                if dt:
                    stamps[s.key] = dt
        if len(set(stamps.values())) > 1:
            newest = max(stamps.values())
            stale = [s for s in sources if s.key in stamps and stamps[s.key] != newest]
            print("  Produced stamps differ; refetching %d page(s) once: %s" %
                  (len(stale), ", ".join(s.page for s in stale)))
            for s in stale:
                results[s.key] = fetcher.get(s.url)
    all_sources = list(sources)
    for _ in range(3):  # index -> semester page -> fragment needs two rounds
        found = eecs_updates.discover(all_sources, results) + \
            action_learning.discover(all_sources, results)
        new = [s for s in dict.fromkeys(found) if s.key not in results]
        if not new:
            break
        for s in new:
            _get(s, refresh, fetcher, results)
            all_sources.append(s)
    return all_sources, results


# ---------------------------------------------------------------------------
# Secondary sources: a failure keeps the last good extract (published, exit 2)
# ---------------------------------------------------------------------------
def _page_ok(source, res):
    return (res is not None and res.ok and len(res.body) >= source.min_bytes and
            not guardrails.is_login_page(res))


def secondary(name, kind, sources, results, parse, archive_dir, drop_check=True):
    """Run parse(last_good) for one secondary source; on failure return the last good extract
    (marked _fallback) with a warning, or a failing extract if there is none."""
    last = extracts.load(archive_dir, name) if archive_dir else None
    try:
        fresh = parse(last)
    except Exception as e:
        traceback.print_exc()
        fresh = {"records": [], "problems": [("fail", "parser crashed: %s: %s" %
                                              (type(e).__name__, e))]}
    problems = [tuple(p) for p in fresh.get("problems", [])]
    reasons = [m for lvl, m in problems if lvl == "fail"]
    reasons += ["%s not fetched" % s.key for s in sources
                if s.kind == kind and not _page_ok(s, results.get(s.key))]
    if not reasons and drop_check and last and last.get("records"):
        before, now = len(last["records"]), len(fresh.get("records", []))
        if now < before * (1 - pconfig.MAX_DROP):
            reasons.append("records dropped from %d to %d" % (before, now))
    keep = [p for p in problems if p[0] != "fail"]
    if not reasons:
        fresh["problems"] = keep
        return fresh
    if last:
        last["problems"] = [("warn", "%s: %s; kept last good extract (run %s)" %
                             (name, "; ".join(reasons), last.get("run_id")))] + \
            [p for p in keep if p[0] == "info"]
        last["_fallback"] = True
        return last
    fresh["problems"] = [("fail", "%s: %s (no earlier extract to fall back on)" %
                          (name, "; ".join(reasons)))] + keep
    return fresh


# ---------------------------------------------------------------------------
# Course rows from secondary sources (until ticket 3 builds the offerings model)
# ---------------------------------------------------------------------------
_UNITS3_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)")


def _num(x):
    v = float(x)
    return int(v) if v.is_integer() else v


def _units(raw):
    """'3-0-9', '3–0–9', '3 - 0 - 9', '12 units (3-1.5-7.5)', '12' -> (units_raw, units, total)."""
    raw = raw or ""
    m = _UNITS3_RE.search(raw)
    if m:
        lec, lab, prep = (_num(g) for g in m.groups())
        return ("%s-%s-%s" % (lec, lab, prep), {"lec": lec, "lab": lab, "prep": prep},
                _num(lec + lab + prep))
    m = re.match(r"\s*(\d+)", raw)
    empty = {"lec": None, "lab": None, "prep": None}
    return (m.group(1), empty, int(m.group(1))) if m else (None, empty, None)


_SCHED_RE = re.compile(r"^(?:(Lecture|Lab|Recitation):\s*)?([MTWRF]+)\s*(\d{1,2}(?:[.:]\d{2})?)\s*-\s*"
                       r"(\d{1,2}(?:[.:]\d{2})?)\s*(pm)?\s*(?:,\s*room\s+([\w-]+)|\(([\w-]+)\))?",
                       re.I)


def _clock(t, pm):
    t = t.replace(":", ".")
    if not pm:
        return catalog._to_24h(t)
    h, _, m = t.partition(".")
    h = int(h) + (12 if int(h) < 12 else 0)
    return "%02d:%02d" % (h, int(m or 0))


def pretty_schedule(raw):
    """'W11-1, room 32-144' -> 'Lecture: Wed 11:00–13:00 (32-144)'; anything else stays raw."""
    raw = (raw or "").strip()
    m = _SCHED_RE.match(raw)
    if not m:
        return raw
    kind, days, start, end, pm, room1, room2 = m.groups()
    days = "/".join(catalog.DAY_NAMES.get(d, d) for d in days.upper())
    out = "%s: %s %s–%s" % (kind or "Lecture", days, _clock(start, pm), _clock(end, pm))
    if room1 or room2:
        out += " (%s)" % (room1 or room2)
    rest = raw[m.end():].strip(" ;,")
    return out + (" | " + rest if rest else "")


def clean_instructors(raw):
    """'Omar Khattab (EECS) Alex Matveev (Outside lecturer)' -> 'Omar Khattab, Alex Matveev'."""
    names = re.findall(r"\s*([^()]+?)\s*\([^)]*\)", raw or "")
    return ", ".join(n.strip(" ,;") for n in names) if names else (raw or None)


def research_area(satisfies, areas):
    """First catalog research area named in the EECS 'Satisfies' line, else 'Special Subject'."""
    text = (satisfies or "").lower()
    hits = [(text.find(a.lower()), a) for a in areas if a.lower() in text]
    return min(hits)[1] if hits else "Special Subject"


def special_subject_course(rec, index_records, areas=()):
    units_raw, units, total = _units(rec.get("units_raw"))
    prefix = rec["numbers"][0].split(".")[0]
    return {
        "number": rec["number"], "title": rec["title"],
        "department": catalog_index.department_name(prefix, index_records),
        "category": research_area(rec.get("satisfies"), areas),
        "terms": [rec["term"].split()[0]],
        "offering_status": "Offered", "offering_notes": [], "meets_with": [],
        "prereq_raw": rec.get("prereq_raw", ""),
        "prereq_numbers": dedupe(catalog.NUM_RE.findall(rec.get("prereq_raw", "") or "")),
        "prereqs": [], "units_raw": units_raw, "units": units, "units_total": total,
        "schedule": [], "schedule_summary": pretty_schedule(rec.get("schedule_raw")),
        "description": rec.get("description", ""),
        "instructor": clean_instructors(rec.get("instructors")),
        "source_page": rec.get("_page") or (rec.get("_src") or {}).get("page"),
        "url": rec.get("url"),
        "eval_status": None, "eval_hours_in": None, "eval_hours_out": None,
        "eval_responses": None, "eval_term": None, "eval_instructor": None,
        "eval_instructor_match": None, "eval_url": None,
        "rating": None, "rating_rationale": None, "aags": "Not approved",
        "is_special": True,
    }


def lab_code(d):
    """Short badge text: a hyphenated code (A-LAB), a short label (LWI, ASEAN LAB), or the
    initials of a long label (INVESTMENT MANAGEMENT LAB -> IM-LAB)."""
    code = d.get("code") or ""
    if "-LAB" in code or len(code) <= 12:
        return code
    words = [w for w in re.findall(r"[A-Z]+", code) if w not in ("IN", "AND", "OF", "THE", "LAB")]
    return "".join(w[0] for w in words) + "-LAB"


def pretty_term(t):
    return "+".join(p.title() if p != "IAP" else p for p in re.split(r"\+", t)) if t else ""


def build(sources, results, archive_dir=None):
    """Parse every source into its extract, then build the data.js payload from them.

    Returns (payload, extracts dict). The payload keeps today's data.js shape.
    """
    def page(key):
        r = results.get(key)
        return r.text() if r is not None else ""

    ex = {}
    ex["catalog_index"] = secondary(
        "catalog_index", "catalog-index", sources, results,
        lambda last: catalog_index.extract(page(pconfig.CATALOG_INDEX_SOURCE.key)), archive_dir)
    ex["eecs_updates"] = secondary(
        "eecs_updates", "eecs-updates", sources, results,
        lambda last: eecs_updates.extract(sources, results), archive_dir, drop_check=False)
    special = [r for r in ex["eecs_updates"]["records"] if "Graduate" in (r.get("level") or "")]

    print("Parsing catalog...")
    cat_pages = {s.page: results[s.key].text() for s in sources if s.kind == "catalog"}
    own = {n for r in special for n in r["numbers"]}
    cat = catalog.extract(cat_pages, own_numbers=own)
    ex["catalog"] = cat
    years = cat["years"]
    print("  %s (academic year %s): %d graduate courses + %d Common Ground" %
          (years["term"], years["this"], cat["counts"]["departments"],
           cat["counts"]["common_ground"]))
    aags_src = next(s for s in sources if s.kind == "aags")
    ag = aags.extract(results[aags_src.key].text())
    ex["aags"] = ag
    print("  AAGS: %d approved subjects" % len(ag["records"]))

    ex["design"] = secondary(
        "design", "design", sources, results,
        lambda last: design.extract(page(pconfig.DESIGN_SOURCE.key)), archive_dir)
    ex["action_learning"] = secondary(
        "action_learning", "action-learning", sources, results,
        lambda last: action_learning.extract(sources, results, last), archive_dir)

    courses = [dict(r) for r in cat["records"]]
    in_catalog = {c["number"] for c in courses}

    # EECS special subjects not in the catalog (catalog rows win).
    added = 0
    areas = sorted({c["category"] for c in courses if c["department"] == "Course 6 — EECS" and
                    c.get("category") and not c["category"].startswith("Common Ground")})
    for r in special:
        if not any(n in in_catalog for n in r["numbers"]):
            courses.append(special_subject_course(r, ex["catalog_index"]["records"], areas))
            added += 1
    print("  EECS subject updates: %d graduate subjects, %d added (not in catalog)" %
          (len(special), added))

    # Resolve prereq names from the full catalog (grad + undergrad subjects).
    name_by_num = cat["all_titles"]
    for c in courses:
        c["prereqs"] = [{"number": n, "name": name_by_num.get(n, "")}
                        for n in c["prereq_numbers"]]

    # AAGS status comes ONLY from the AAGS page.
    aags_depts = {d["name"] for d in pconfig.CATALOG_DEPARTMENTS if d["aags"]}
    status = {r["number"]: r["status"] for r in ag["records"]}
    for c in courses:
        if c["number"] in status:
            c["aags"] = status[c["number"]]
        elif c["department"] in aags_depts:
            c["aags"] = "Not approved"
        else:
            c["aags"] = "N/A"  # non-EECS course not on the AAGS page

    # Evaluation hours (evals.json, refreshed once per term by a logged-in browser run).
    ev_ex, ev_problems = evals.load(os.path.join(HERE, "evals.json"))
    ev_ex["problems"] = ev_problems
    ex["evals"] = ev_ex
    by_num = {r["number"]: r for r in ev_ex["records"]}
    for c in courses:
        r = by_num.get(c["number"])
        if r:
            c.update(evals.legacy_fields(r))
    print("  applied evaluation data for %d courses" %
          sum(1 for c in courses if c["eval_status"]))

    # Personal ratings are NOT merged here: data.js is public. They load at runtime from the
    # gitignored personal/ratings.js overlay (see index.html), so they can never be published.

    # LGO pre-approved design classes (conditional wins; see pipeline/sources/design.py).
    dz, notes = design.resolve(ex["design"]["records"], courses)
    ex["design"]["problems"] = list(ex["design"].get("problems", [])) + \
        [("info", n) for n in notes]
    for c in courses:
        c["design_approved"] = dz.get(c["number"])
    print("  flagged %d design classes (%d conditional)" %
          (len(dz), sum(1 for v in dz.values() if v == "conditional")))

    # Action Learning labs (booklet; see pipeline/sources/action_learning.py).
    labs, notes = action_learning.resolve(ex["action_learning"], courses, years["this"])
    ex["action_learning"]["problems"] = list(ex["action_learning"].get("problems", [])) + \
        [("info", n) for n in notes]
    for c in courses:
        d = labs.get(c["number"])
        c["action_learning"] = lab_code(d) if d else None
        if d:
            c["al_name"] = d.get("name") or c["title"]
            c["al_term"] = pretty_term(d.get("term"))
            if d["status"] != "confirmed":
                c["al_status"] = d["status"]
            if (not c["title"]) or re.search(r"Special (Seminar|Distance)", c["title"]):
                c["title"] = "%s (%s)" % (d.get("name") or c["title"], lab_code(d))
    print("  tagged %d Action Learning labs" % sum(1 for c in courses if c["action_learning"]))

    meta = {
        "pulled_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "catalog_term": years["term"],
        "academic_year": years["this"],
        "source_dates": cat["page_dates"],
        "aags_count": len(ag["records"]),
        "course_count": len(courses),
        "departments": dict(Counter(c["department"] for c in courses)),
    }
    payload = {"meta": meta, "courses": courses}
    return payload, ex


def write_outputs(payload):
    courses, meta = payload["courses"], payload["meta"]
    with open(os.path.join(HERE, "courses.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with open(os.path.join(HERE, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.COURSE_DATA = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";\n")

    print("Wrote courses.json and data.js  (pulled_at %s)" % meta["pulled_at"])
    offered = sum(1 for c in courses if c["offering_status"] == "Offered")
    print("  offered now: %d  |  AAGS-approved in set: %d" %
          (offered, sum(1 for c in courses if c["aags"] != "Not approved")))


def _arg_value(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        sys.exit("%s needs a value" % flag)
    return None


def main(fetcher=None):
    refresh = "--refresh" in sys.argv
    archive_dir = _arg_value("--archive-dir") or pconfig.ARCHIVE_DIR
    archive = None
    if os.path.isdir(archive_dir):
        archive = snapshots.Archive(archive_dir)
    elif refresh and "--no-archive" not in sys.argv:
        print("Note: no archive at %s; snapshots will not be saved." % archive_dir)
    started = datetime.now(timezone.utc)
    run_id = snapshots.stamp(started)

    sources = pconfig.build_sources(pconfig.catalog_pages())
    print("Collecting %d pages + discovered links (%s)..." %
          (len(sources), "live" if refresh else "cache"))
    sources, results = collect(sources, refresh, fetcher)
    pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in sources}
    baseline = archive.baseline_run() if archive else None

    payload, ex, courses_info, parse_error = None, {}, None, None
    try:
        payload, ex = build(sources, results, archive_dir if archive else None)
        courses_info = guardrails.course_metrics(ex["catalog"]["records"],
                                                 len(ex["aags"]["records"]))
    except Exception as e:  # a page redesign can break the parser; that's a failed run
        traceback.print_exc()
        parse_error = "%s: %s" % (type(e).__name__, e)

    checks = guardrails.evaluate(sources, results, pages, courses_info, baseline, parse_error)
    for name, e in ex.items():
        checks += guardrails.problem_checks(name, e.get("problems", []))
    years = ex.get("catalog", {}).get("years", {})
    if years.get("this"):
        checks.append(guardrails.Check("catalog_year", "run", True, "%s -> academic year %s" %
                                       (years.get("term") or "term unknown", years["this"])))
    ok = guardrails.passed(checks)
    warned = [c for c in checks if not c.ok and c.level == "warn"]
    print(guardrails.summary_table(sources, pages, checks, baseline))

    if ok:
        print("\nAll %d guardrail checks passed%s." %
              (len(checks), " (%d warning(s))" % len(warned) if warned else ""))
        for s in sources:
            if results[s.key].via != "cache":
                _save_cache(s, results[s.key])
        write_outputs(payload)
    else:
        print("\nGuardrails FAILED - nothing written (courses.json / data.js unchanged).")

    if archive and refresh and "--no-archive" not in sys.argv:
        status = "pass" if ok else "fail"
        stored = unchanged = 0
        entries = {}
        for s in sources:
            entry = archive.record(run_id, s, results[s.key], status,
                                   produced=pages[s.key].get("produced"),
                                   login=pages[s.key].get("login", False))
            entries[s.key] = entry
            stored += "stored" in entry
            unchanged += "unchanged_since" in entry
        if ok:
            written = extracts.write_all(archive_dir, run_id, sources, entries, ex)
            kept = [n for n, e in ex.items() if e.get("_fallback")]
            print("Wrote extracts: %s%s" % (", ".join(written),
                                             "; kept last good: %s" % ", ".join(kept)
                                             if kept else ""))
        archive.record_run(guardrails.run_record(
            run_id, snapshots.iso(started), snapshots.iso(datetime.now(timezone.utc)),
            sources, pages, courses_info, checks, published=ok))
        print("Archived run %s (%s) to %s: %d page(s) saved, %d unchanged." %
              (run_id, status, archive_dir, stored, unchanged))
    return 1 if not ok else (2 if warned else 0)


if __name__ == "__main__":
    sys.exit(main())
