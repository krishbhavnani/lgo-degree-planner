#!/usr/bin/env python3
"""
Scraper for the MIT Course 6 (EECS) graduate-course dashboard.

Pulls the four public catalog pages (m6a-m6d) and the public EECS AAGS
degree-requirements page, parses GRADUATE subjects only, and writes:

    courses.json   - structured data (for inspection / portability)
    data.js        - `window.COURSE_DATA = {...}` (loaded by index.html offline)

Course-evaluation hours come from evals.json and are merged in on every run.
Personal ratings are never merged into data.js (it is public); they load at
runtime from the gitignored personal/ratings.js overlay. Browser flags live in localStorage and are untouched.

Every run goes through the pipeline/ package:
  - polite fetching (identifying user agent, 1.5 s per-host delay, retries, curl fallback)
  - guardrails: if any sanity check fails, nothing is written and the script exits non-zero
  - with --refresh, raw pages are archived (change-only, gzipped) into .data/, a local
    worktree of the public `data` branch. The archive is written but never committed here.

Stdlib only - no third-party packages required.
Run:  python3 scrape.py              # parse cached pages in .scratch/ (fetches any missing)
      python3 scrape.py --refresh    # fetch live from MIT, archive, check, publish
      python3 scrape.py --refresh --archive-dir PATH   # archive somewhere else
      python3 scrape.py --refresh --no-archive
"""

import html
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone

from pipeline import config as pconfig
from pipeline import guardrails, snapshots
from pipeline.fetch import Fetcher, FetchResult

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".scratch")
CATALOG_URL = pconfig.CATALOG_URL
AAGS_URL = pconfig.AAGS_URL

# Departments to scrape. `code` is the subject-number prefix and the OSE department id;
# `aags` flags the EECS AAGS approved-subject list (only meaningful for Course 6).
DEPARTMENTS = [
    {"code": "6", "name": "Course 6 — EECS", "pages": ["m6a", "m6b", "m6c", "m6d"], "aags": True},
    {"code": "15", "name": "Course 15 — Management", "pages": ["m15a", "m15b", "m15c"], "aags": False},
    {"code": "2", "name": "Course 2 — MechE", "pages": ["m2a", "m2b", "m2c"], "aags": False},
]

# Catalog years referenced in icon alt text (used to label offering status).
THIS_AY = "2026-2027"
NEXT_AY = "2027-2028"

# Pages collected for this run (cache_name -> FetchResult), filled by collect().
_PAGES = {}


def fetch(url, cache_name, refresh=False):
    """Return a page collected for this run (see collect()). Parsers call this."""
    if cache_name not in _PAGES:
        raise RuntimeError("%s is not in the source registry (pipeline/config.py)" % cache_name)
    return _PAGES[cache_name].text()


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
    _PAGES.clear()
    for s in sources:
        _PAGES[s.cache_name] = results[s.key]
    return results


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Schedule parsing
# ---------------------------------------------------------------------------
DAY_NAMES = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri", "S": "Sat"}


def _to_24h(num):
    """MIT time grid: 8-12 are AM/noon, 1-7 are PM."""
    if "." in num:
        hpart, mpart = num.split(".", 1)
        hour = int(hpart)
        minute = int(mpart)
    else:
        hour = int(num)
        minute = 0
    if 1 <= hour <= 7:
        hour += 12
    return "%02d:%02d" % (hour, minute)


def parse_time_code(code):
    """'TR11-12.30' -> (['Tue','Thu'], '11:00', '12:30'). 'F10' -> (['Fri'],'10:00',None)."""
    code = code.strip()
    m = re.match(r"^([MTWRFS]+)\s*([0-9.]+)?(?:-([0-9.]+))?", code)
    if not m:
        return ([], None, None)
    days = [DAY_NAMES.get(c, c) for c in m.group(1)]
    start = _to_24h(m.group(2)) if m.group(2) else None
    end = _to_24h(m.group(3)) if m.group(3) else None
    return (days, start, end)


def parse_schedule(segment):
    """Parse the Lecture/Lab/Recitation segment into structured components."""
    if not segment:
        return []
    # Split on the bold component labels, keeping the label.
    parts = re.split(r"<b>\s*(Lecture|Lab|Recitation)\s*:\s*</b>", segment)
    comps = []
    # parts = [pre, 'Lecture', body, 'Lab', body, ...]
    for i in range(1, len(parts), 2):
        kind = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # First italic time code (e.g. <i>TR11-12.30</i>); ignore <b>+final</b> etc.
        codes = re.findall(r"<i>\s*([^<]+?)\s*</i>", body, flags=re.I)
        codes = [c for c in codes if not c.lower().startswith("+")]
        raw = strip_tags(body)
        days, start, end = ([], None, None)
        primary = codes[0] if codes else ""
        if primary and primary.upper() != "TBA":
            days, start, end = parse_time_code(primary)
        comps.append({
            "kind": kind,
            "code": primary,
            "days": days,
            "start": start,
            "end": end,
            "raw": raw,
        })
    return comps


def schedule_summary(comps):
    """Human-readable one-liner for the table cell."""
    out = []
    for c in comps:
        if c["days"] and c["start"]:
            t = "/".join(c["days"]) + " " + c["start"]
            if c["end"]:
                t += "–" + c["end"]
            out.append("%s: %s" % (c["kind"], t))
        elif c["code"]:
            out.append("%s: %s" % (c["kind"], c["code"]))
        else:
            out.append(c["kind"])
    return " | ".join(out)


# ---------------------------------------------------------------------------
# Offering status
# ---------------------------------------------------------------------------
def offering_status(body):
    notes = []
    if 'alt="Not offered academic year %s"' % THIS_AY in body:
        status = "Not offered this year (%s)" % THIS_AY
    elif 'alt="Not offered academic year %s"' % NEXT_AY in body:
        status = "Not offered next year (%s)" % NEXT_AY
    elif "nooffera.gif" in body or "Not currently listed" in body:
        status = "Not currently listed in schedule"
    else:
        status = "Offered"
    if "Not offered regularly; consult department" in body:
        notes.append("Not offered regularly; consult department")
    return status, notes


# ---------------------------------------------------------------------------
# Course block parsing
# ---------------------------------------------------------------------------
H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.I | re.S)
BLOCK_RE = re.compile(r'<a name="(\d+\.[^"]+)"></a>(.*?)<!--end-->', re.I | re.S)
NUM_RE = re.compile(r"\b\d+\.[A-Za-z0-9]+\b")


def categories_by_pos(page_html):
    return [(m.start(), strip_tags(m.group(1))) for m in H2_RE.finditer(page_html)]


def category_for(cats, pos):
    cat = None
    for cpos, name in cats:
        if cpos < pos:
            cat = name
        else:
            break
    return cat


def parse_block(number, body, category, page, department):
    is_grad = 'alt="Graduate"' in body
    if not is_grad:
        return None  # skip undergraduate subjects

    # Title: text in <h3> after the number, up to the <br> underline.
    title = ""
    mt = re.search(r"<h3[^>]*>\s*" + re.escape(number) + r"\s*(.*?)(?:<br>|</h3>)",
                   body, re.I | re.S)
    if mt:
        title = strip_tags(mt.group(1))

    terms = []
    for t in ("Fall", "IAP", "Spring", "Summer"):
        if 'alt="%s"' % t in body:
            terms.append(t)

    status, notes = offering_status(body)

    meets_with = []
    mm = re.search(r"Subject meets with\s*(.*?)<br>", body, re.I | re.S)
    if mm:
        meets_with = dedupe(NUM_RE.findall(strip_tags(mm.group(1))))

    # Prereq line (raw text + extracted numbers; dedupe, parse from clean text)
    prereq_raw = ""
    prereq_nums = []
    mp = re.search(r"Prereq:\s*(.*?)<br>", body, re.I | re.S)
    if mp:
        prereq_raw = strip_tags(mp.group(1))
        prereq_nums = dedupe(NUM_RE.findall(prereq_raw))

    # Units
    units_raw = None
    units = {"lec": None, "lab": None, "prep": None}
    units_total = None
    mu = re.search(r"Units:\s*(\d+)-(\d+)-(\d+)", body)
    if mu:
        units_raw = "%s-%s-%s" % mu.groups()
        units = {"lec": int(mu.group(1)), "lab": int(mu.group(2)),
                 "prep": int(mu.group(3))}
        units_total = sum(int(g) for g in mu.groups())

    # Schedule: the segment that contains the component labels, ending at <!--s-->.
    schedule = []
    ms = re.search(r"(<b>\s*(?:Lecture|Lab|Recitation).*?)<!--s-->", body, re.I | re.S)
    if ms:
        schedule = parse_schedule(ms.group(1))

    # Description + instructor: everything after the SECOND hr.gif divider.
    hrs = [m.end() for m in re.finditer(r'<img[^>]*hr\.gif[^>]*>', body, re.I)]
    description = ""
    instructor = None
    if len(hrs) >= 2:
        tail = body[hrs[1]:]
        mi = re.search(r"<I>\s*(.*?)\s*</I>", tail, re.I | re.S)
        if mi:
            instructor = strip_tags(mi.group(1))
            desc_part = tail[:mi.start()]
        else:
            desc_part = tail
        description = strip_tags(desc_part)
        # Drop trailing textbook boilerplate if it leaked in.
        description = re.sub(r"\s*No textbook information available\s*$", "",
                             description).strip()

    return {
        "number": number,
        "title": title,
        "department": department,
        "category": category,
        "terms": terms,
        "offering_status": status,
        "offering_notes": notes,
        "meets_with": meets_with,
        "prereq_raw": prereq_raw,
        "prereq_numbers": prereq_nums,  # names resolved in a later pass
        "prereqs": [],
        "units_raw": units_raw,
        "units": units,
        "units_total": units_total,
        "schedule": schedule,
        "schedule_summary": schedule_summary(schedule),
        "description": description,
        "instructor": instructor,
        "source_page": page,
        "url": "https://student.mit.edu/catalog/%s.html#%s" % (page, number),
        # eval / rating placeholders (filled by later steps; merged on rerun)
        "eval_status": None,
        "eval_hours_in": None,
        "eval_hours_out": None,
        "eval_responses": None,
        "eval_term": None,
        "eval_instructor": None,
        "eval_instructor_match": None,
        "eval_url": None,
        "rating": None,
        "rating_rationale": None,
        "aags": "Not approved",
    }


TITLE_RE = re.compile(r"<h3[^>]*>\s*(\d+\.[A-Za-z0-9]+)\s*(.*?)(?:<br>|</h3>)", re.I | re.S)


def parse_catalog(refresh=False):
    courses = []
    page_dates = {}
    all_titles = {}  # every subject (grad + undergrad) -> title, for prereq names
    for dept in DEPARTMENTS:
        prefix = dept["code"] + "."
        for page in dept["pages"]:
            page_html = fetch(CATALOG_URL.format(page), "%s.html" % page, refresh)
            md = re.search(r"Produced:\s*([^<]+)", page_html)
            if md:
                page_dates[page] = md.group(1).strip()
            for tm in TITLE_RE.finditer(page_html):
                all_titles[tm.group(1)] = strip_tags(tm.group(2))
            cats = categories_by_pos(page_html)
            for m in BLOCK_RE.finditer(page_html):
                number, body = m.group(1), m.group(2)
                if not number.startswith(prefix):
                    continue  # skip cross-listed subjects from other departments
                cat = category_for(cats, m.start())
                rec = parse_block(number, body, cat, page, dept["name"])
                if rec:
                    courses.append(rec)
    return courses, page_dates, all_titles


# ---------------------------------------------------------------------------
# Common Ground for Computing Education (cross-department "X.C##" subjects)
# ---------------------------------------------------------------------------
# These live on their own catalog page (mCGa) under CG.### anchors, plus a
# "Common Ground" section of m6e. Each block names its real subject number in
# the <h3>. A class can be jointly listed under several departments ("Same
# subject as ..."). Like other joint classes in this dataset, we keep one row per
# covered department; a class with no covered-department number gets one row.
CG_SOURCES = [("mCGa", None), ("m6e", "Common Ground for Computing Education")]
CG_OTHER_DEPT = "Common Ground — other depts"
CG_NUM_RE = re.compile(r"\b[0-9A-Z]+\.[0-9A-Z]+\b")


def parse_common_ground(existing_numbers, refresh=False):
    covered = {d["code"]: d["name"] for d in DEPARTMENTS}
    seen = set(existing_numbers)
    out, page_dates = [], {}
    for page, section in CG_SOURCES:
        page_html = fetch(CATALOG_URL.format(page), "%s.html" % page, refresh)
        md = re.search(r"Produced:\s*([^<]+)", page_html)
        if md:
            page_dates[page] = md.group(1).strip()
        cats = categories_by_pos(page_html)
        for m in re.finditer(r'<a name="([^"]+)"></a>(.*?)<!--end-->', page_html, re.I | re.S):
            anchor, body = m.group(1), m.group(2)
            cat = category_for(cats, m.start())
            if section and cat != section:
                continue
            mh = re.search(r"<h3[^>]*>\s*([0-9A-Z]+\.[0-9A-Z]+)", body)
            if not mh or ".C" not in mh.group(1):
                continue
            num = mh.group(1)
            ms = re.search(r"\(Same subject as(.*?)\)", body, re.S)
            joint = CG_NUM_RE.findall(strip_tags(ms.group(1))) if ms else []
            prefix = num.split(".")[0]
            if prefix in covered:
                if num in seen:
                    continue
                dept = covered[prefix]
            else:
                if any(j.split(".")[0] in covered for j in joint) or \
                   any(x in seen for x in [num] + joint):
                    # mark only non-covered numbers; covered ones get their own row
                    seen.update(x for x in [num] + joint if x.split(".")[0] not in covered)
                    continue
                dept = CG_OTHER_DEPT
            category = "Common Ground: " + cat if (page == "mCGa" and cat) else "Common Ground"
            rec = parse_block(num, body, category, page, dept)
            seen.add(num)
            if prefix not in covered:
                seen.update(joint)
            if not rec:
                continue  # undergraduate
            rec["url"] = CATALOG_URL.format(page) + "#" + anchor
            rec["common_ground"] = True
            out.append(rec)
    return out, page_dates


# ---------------------------------------------------------------------------
# AAGS approval status
# ---------------------------------------------------------------------------
def parse_aags(refresh=False):
    """Return {course_number: status} from color coding, for EVERY subject on the
    AAGS page (any department — e.g. the 6.C51 co-requisite modules like 15.C51).
    The AAGS page is the only source of truth for AAGS status.

    blue  -> Approved-Offered, grey -> Approved-NotThisYear,
    black -> Approved-NotInCatalog (in AAGS list but absent from catalog).
    """
    page = fetch(AAGS_URL, "aags.html", refresh)
    status = {}
    # Each course link carries an inline color style and a search=NUMBER href.
    for m in re.finditer(r'style="[^"]*color:(blue|grey|black)[^"]*"[^>]*href="[^"]*search=([A-Za-z0-9]+\.[A-Za-z0-9]+)"',
                         page):
        color, num = m.group(1), m.group(2)
        status[num] = color
    # Some pages place href before style; try the reverse order too.
    for m in re.finditer(r'href="[^"]*search=([A-Za-z0-9]+\.[A-Za-z0-9]+)"[^>]*style="[^"]*color:(blue|grey|black)',
                         page):
        num, color = m.group(1), m.group(2)
        status.setdefault(num, color)
    label = {"blue": "Approved-Offered", "grey": "Approved-NotThisYear",
             "black": "Approved-NotInCatalog"}
    return {num: label[c] for num, c in status.items()}


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
    prereq_nums = dedupe(NUM_RE.findall(e.get("prereq_raw", "") or ""))
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


def build():
    """Parse the collected pages and merge sidecar data.

    Returns (payload, scraped, aags_count): `scraped` is the catalog + Common Ground courses
    only (before hand-added extras), which the guardrails check.
    """
    print("Parsing catalog...")
    courses, page_dates, all_titles = parse_catalog()
    print("  parsed %d graduate courses" % len(courses))

    cg, cg_dates = parse_common_ground({c["number"] for c in courses})
    courses.extend(cg)
    page_dates.update(cg_dates)
    print("  added %d Common Ground graduate courses" % len(cg))
    scraped = list(courses)

    # Resolve prereq names from the full catalog (grad + undergrad subjects).
    # Append hand-added courses (special subjects, etc.) before downstream processing.
    extra = load_extra()
    for e in extra:
        courses.append(expand_extra(e))
    if extra:
        print("  added %d extra/special-subject courses" % len(extra))

    name_by_num = all_titles
    for c in courses:
        c["prereqs"] = [{"number": n, "name": name_by_num.get(n, "")}
                        for n in c["prereq_numbers"]]

    # AAGS status comes ONLY from the AAGS page (never from extra.json or elsewhere).
    aags_depts = {d["name"] for d in DEPARTMENTS if d["aags"]}
    print("Parsing AAGS approvals...")
    aags = parse_aags()
    for c in courses:
        if c["number"] in aags:
            c["aags"] = aags[c["number"]]
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

    from collections import Counter
    dept_counts = Counter(c["department"] for c in courses)
    meta = {
        "pulled_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_dates": page_dates,
        "aags_count": len(aags),
        "course_count": len(courses),
        "departments": dict(dept_counts),
    }
    payload = {"meta": meta, "courses": courses}
    return payload, scraped, len(aags)


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

    catalog_pages = [p for d in DEPARTMENTS for p in d["pages"]] + [p for p, _ in CG_SOURCES]
    sources = pconfig.build_sources(catalog_pages)
    print("Collecting %d pages (%s)..." % (len(sources), "live" if refresh else "cache"))
    results = collect(sources, refresh, fetcher)
    pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in sources}
    baseline = archive.baseline_run() if archive else None

    payload, courses_info, parse_error = None, None, None
    try:
        payload, scraped, aags_count = build()
        courses_info = guardrails.course_metrics(scraped, aags_count)
    except Exception as e:  # a page redesign can break the parser; that's a failed run
        traceback.print_exc()
        parse_error = "%s: %s" % (type(e).__name__, e)

    checks = guardrails.evaluate(sources, results, pages, courses_info, baseline, parse_error)
    ok = guardrails.passed(checks)
    print(guardrails.summary_table(sources, pages, checks, baseline))

    if ok:
        print("\nAll %d guardrail checks passed." % len(checks))
        for s in sources:
            if results[s.key].via != "cache":
                _save_cache(s, results[s.key])
        write_outputs(payload)
    else:
        print("\nGuardrails FAILED - nothing written (courses.json / data.js unchanged).")

    if archive and refresh and "--no-archive" not in sys.argv:
        status = "pass" if ok else "fail"
        stored = unchanged = 0
        for s in sources:
            entry = archive.record(run_id, s, results[s.key], status,
                                   produced=pages[s.key].get("produced"),
                                   login=pages[s.key].get("login", False))
            stored += "stored" in entry
            unchanged += "unchanged_since" in entry
        archive.record_run(guardrails.run_record(
            run_id, snapshots.iso(started), snapshots.iso(datetime.now(timezone.utc)),
            sources, pages, courses_info, checks, published=ok))
        print("Archived run %s (%s) to %s: %d page(s) saved, %d unchanged." %
              (run_id, status, archive_dir, stored, unchanged))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
