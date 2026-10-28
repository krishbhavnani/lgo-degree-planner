#!/usr/bin/env python3
"""
Builds the LGO Degree Planner course data (data.js / courses.json).

Pipeline (see pipeline/):
  1. collect   fetch every registered source politely (or read the .scratch/ cache)
  2. extract   each source module parses its pages into a normalized extract
               (pipeline/sources/catalog.py, aags.py)
  3. check     guardrails; any failure -> nothing written, exit 1
  4. archive   with --refresh: raw pages saved change-only, gzipped, into .data/ (a worktree of
               the public `data` branch), plus extracts/ written from passing runs. Never
               committed by this script.
  5. publish   data.js / courses.json, built from the extracts plus the small public sidecar
               files (evals.json, design.json, al.json, extra.json).

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
from pipeline.sources import aags, catalog
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


def collect(sources, refresh, fetcher=None):
    """Fetch every source (live with --refresh, else from .scratch/ cache when present).

    Fetched pages are not written to the .scratch/ cache here; main() does that only after
    the guardrails pass, so a bad fetch never replaces a good cached copy.

    Live catalog pages whose Produced stamp differs from the newest one are refetched once
    (MIT regenerates the listing daily; a fetch can straddle the regeneration).
    """
    fetcher = fetcher or Fetcher()
    results = {}
    for s in sources:
        res = None if refresh else _from_cache(s)
        if res is None:
            res = fetcher.get(s.url)
        results[s.key] = res
        print("  %-14s %s  %4.0f KB%s" % (s.key, res.status, len(res.body) / 1024,
                                          "  (%s)" % res.error if res.error else ""))
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
    return results


# ---------------------------------------------------------------------------
# Merge previous eval/rating values keyed by course number
# ---------------------------------------------------------------------------
EVAL_FIELDS = ("eval_status", "eval_hours_in", "eval_hours_out", "eval_responses",
               "eval_term", "eval_instructor", "eval_instructor_match")


def _load_json(name):
    """Load an optional sidecar JSON keyed by course number (absent is fine)."""
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_evals():
    """evals.json (Chrome-driven OSE scrape) is authoritative for eval fields."""
    return _load_json("evals.json")


def load_design():
    """design.json: LGO pre-approved design classes (approved / conditional)."""
    return _load_json("design.json")


def load_al():
    """al.json: MIT Sloan Action Learning labs (lab code, name, term)."""
    return _load_json("al.json")


def load_extra():
    """extra.json: hand-added courses (e.g. special subjects) not in the catalog pages."""
    path = os.path.join(HERE, "extra.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


PAGE_FALL26 = "https://www.eecs.mit.edu/academics/subject-updates/subject-updates-fall-2026/"


def expand_extra(e):
    """Turn a minimal extra.json entry into a full course record."""
    units = {"lec": None, "lab": None, "prep": None}
    total = None
    mu = re.match(r"(\d+)-(\d+)-(\d+)$", e.get("units_raw", "") or "")
    if mu:
        units = {"lec": int(mu.group(1)), "lab": int(mu.group(2)), "prep": int(mu.group(3))}
        total = sum(int(g) for g in mu.groups())
    elif (e.get("units_raw") or "").isdigit():
        total = int(e["units_raw"])
    prereq_nums = dedupe(catalog.NUM_RE.findall(e.get("prereq_raw", "") or ""))
    return {
        "number": e["number"], "title": e["title"], "department": e["department"],
        "category": e.get("category"), "terms": e.get("terms", []),
        "offering_status": e.get("offering_status", "Offered"), "offering_notes": [],
        "meets_with": [], "prereq_raw": e.get("prereq_raw", ""), "prereq_numbers": prereq_nums,
        "prereqs": [], "units_raw": e.get("units_raw"), "units": units, "units_total": total,
        "schedule": [], "schedule_summary": e.get("schedule_summary", ""),
        "description": e.get("description", ""), "instructor": e.get("instructor"),
        "source_page": "subject-updates-fall-2026",
        "url": PAGE_FALL26 + ("#" + e["anchor"] if e.get("anchor") else ""),
        "eval_status": None, "eval_hours_in": None, "eval_hours_out": None,
        "eval_responses": None, "eval_term": None, "eval_instructor": None,
        "eval_instructor_match": None, "eval_url": None,
        "rating": None, "rating_rationale": None, "aags": e.get("aags", "Not approved"),
        "is_special": True,
    }


def build(sources, results):
    """Parse every source into its extract, then build the data.js payload from them.

    Returns (payload, extracts dict). The payload keeps today's data.js shape.
    """
    print("Parsing catalog...")
    cat_pages = {s.page: results[s.key].text() for s in sources if s.kind == "catalog"}
    cat = catalog.extract(cat_pages)
    years = cat["years"]
    print("  %s (academic year %s): %d graduate courses + %d Common Ground" %
          (years["term"], years["this"], cat["counts"]["departments"],
           cat["counts"]["common_ground"]))
    aags_src = next(s for s in sources if s.kind == "aags")
    ag = aags.extract(results[aags_src.key].text())
    print("  AAGS: %d approved subjects" % len(ag["records"]))

    courses = [dict(r) for r in cat["records"]]

    # Append hand-added courses (special subjects, etc.) before downstream processing.
    extra = load_extra()
    for e in extra:
        courses.append(expand_extra(e))
    if extra:
        print("  added %d extra/special-subject courses" % len(extra))

    # Resolve prereq names from the full catalog (grad + undergrad subjects).
    name_by_num = cat["all_titles"]
    for c in courses:
        c["prereqs"] = [{"number": n, "name": name_by_num.get(n, "")}
                        for n in c["prereq_numbers"]]

    # AAGS status comes ONLY from the AAGS page (never from extra.json or elsewhere).
    aags_depts = {d["name"] for d in pconfig.CATALOG_DEPARTMENTS if d["aags"]}
    status = {r["number"]: r["status"] for r in ag["records"]}
    for c in courses:
        if c["number"] in status:
            c["aags"] = status[c["number"]]
        elif c["department"] in aags_depts:
            c["aags"] = "Not approved"
        else:
            c["aags"] = "N/A"  # non-EECS course not on the AAGS page

    # Apply evaluation data (authoritative) from evals.json.
    evals = load_evals()
    for c in courses:
        ev = evals.get(c["number"])
        if ev:
            for k in EVAL_FIELDS:
                if k in ev:
                    c[k] = ev[k]
    if evals:
        print("  applied evaluation data for %d courses" %
              sum(1 for c in courses if c["eval_status"]))

    # Personal ratings are NOT merged here: data.js is public. They load at runtime from the
    # gitignored personal/ratings.js overlay (see index.html), so they can never be published.

    # Apply LGO pre-approved design-class designation.
    design = load_design()
    approved = set(design.get("approved", []))
    conditional = set(design.get("conditional", []))
    for c in courses:
        c["design_approved"] = ("approved" if c["number"] in approved else
                                "conditional" if c["number"] in conditional else None)
    if design:
        print("  flagged %d design-approved courses" %
              sum(1 for c in courses if c["design_approved"]))

    # Apply Action Learning lab designations (tag + fix generic SSIM titles).
    al = load_al()
    for c in courses:
        info = al.get(c["number"])
        if info:
            c["action_learning"] = info["lab"]
            c["al_name"] = info["name"]
            c["al_term"] = info["term"]
            if (not c["title"]) or re.search(r"Special (Seminar|Distance)", c["title"]):
                c["title"] = "%s (%s)" % (info["name"], info["lab"])
        else:
            c.setdefault("action_learning", None)
    if al:
        print("  tagged %d Action Learning labs" %
              sum(1 for c in courses if c.get("action_learning")))

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
    return payload, {"catalog": cat, "aags": ag}


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
    print("Collecting %d pages (%s)..." % (len(sources), "live" if refresh else "cache"))
    results = collect(sources, refresh, fetcher)
    pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in sources}
    baseline = archive.baseline_run() if archive else None

    payload, ex, courses_info, parse_error = None, {}, None, None
    try:
        payload, ex = build(sources, results)
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
            print("Wrote extracts: %s" % ", ".join(written))
        archive.record_run(guardrails.run_record(
            run_id, snapshots.iso(started), snapshots.iso(datetime.now(timezone.utc)),
            sources, pages, courses_info, checks, published=ok))
        print("Archived run %s (%s) to %s: %d page(s) saved, %d unchanged." %
              (run_id, status, archive_dir, stored, unchanged))
    return 1 if not ok else (2 if warned else 0)


if __name__ == "__main__":
    sys.exit(main())
