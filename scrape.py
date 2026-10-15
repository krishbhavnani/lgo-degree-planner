#!/usr/bin/env python3
"""
Scraper for the MIT Course 6 (EECS) graduate-course dashboard.

Pulls the four public catalog pages (m6a-m6d) and the public EECS AAGS
degree-requirements page, parses GRADUATE subjects only, and writes:

    courses.json   - structured data (for inspection / portability)
    data.js        - `window.COURSE_DATA = {...}` (loaded by index.html offline)

Course-evaluation hours and the subjective rating are filled in by separate
steps (Chrome-driven eval scrape + Claude-authored ratings). This script
MERGES those values from the previous data.js on rerun so a catalog refresh
does not wipe them. Browser flags live in localStorage and are untouched.

Stdlib only (urllib, re, html, json) - no third-party packages required.
Run:  python3 scrape.py
"""

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".scratch")
CATALOG_URL = "https://student.mit.edu/catalog/{}.html"
AAGS_URL = "https://eecsis.mit.edu/degree_requirements.pcgi?program=AAGS"
USER_AGENT = "Mozilla/5.0 (course-dashboard scraper; personal use)"

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


def fetch(url, cache_name, refresh=False):
    """Fetch a URL, caching the raw HTML under .scratch/ for cheap reruns."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, cache_name)
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return data


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
# AAGS approval status
# ---------------------------------------------------------------------------
def parse_aags(refresh=False):
    """Return {course_number: status} from color coding.

    blue  -> Approved-Offered, grey -> Approved-NotThisYear,
    black -> Approved-NotInCatalog (in AAGS list but absent from catalog).
    """
    page = fetch(AAGS_URL, "aags.html", refresh)
    status = {}
    # Each course link carries an inline color style and a search=NUMBER href.
    for m in re.finditer(r'style="[^"]*color:(blue|grey|black)[^"]*"[^>]*href="[^"]*search=(6\.[A-Za-z0-9]+)"',
                         page):
        color, num = m.group(1), m.group(2)
        status[num] = color
    # Some pages place href before style; try the reverse order too.
    for m in re.finditer(r'href="[^"]*search=(6\.[A-Za-z0-9]+)"[^>]*style="[^"]*color:(blue|grey|black)',
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


def load_ratings():
    """ratings.json (Claude-authored) is authoritative for rating + rationale."""
    return _load_json("ratings.json")


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


def main():
    refresh = "--refresh" in sys.argv
    print("Fetching catalog (%s)..." % ("live" if refresh else "cache ok"))
    courses, page_dates, all_titles = parse_catalog(refresh)
    print("  parsed %d graduate courses" % len(courses))

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

    aags_depts = {d["name"] for d in DEPARTMENTS if d["aags"]}
    aags = {}
    if aags_depts:
        print("Fetching AAGS approvals...")
        aags = parse_aags(refresh)
    for c in courses:
        if c["department"] not in aags_depts:
            c["aags"] = "N/A"  # AAGS is an EECS requirement; not applicable
        elif c["number"] in aags:
            c["aags"] = aags[c["number"]]

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

    # Apply Claude-authored ratings (authoritative) from ratings.json.
    ratings = load_ratings()
    for c in courses:
        rt = ratings.get(c["number"])
        if rt:
            for k in ("rating", "rating_rationale"):
                if k in rt:
                    c[k] = rt[k]
    if ratings:
        print("  applied ratings for %d courses" %
              sum(1 for c in courses if c["rating"] is not None))

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


if __name__ == "__main__":
    main()
