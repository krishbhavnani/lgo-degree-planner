"""MIT Subject Listing (student.mit.edu/catalog) -> catalog extract.

Parses graduate subjects from the department pages and the Common Ground pages.

Identity comes from each block's <h3> heading, not the <a name> anchor before it: anchors are
sometimes bunched (a block headed 15.S11 sat under the 15.S10 anchor). A range heading such as
"15.840-15.843 Seminar in Marketing" becomes ONE row labeled with the range; numbers in the
range that have a block of their own get their own row and leave the range.

The academic year is read from the pages ("Not offered academic year 2026-2027" icons) instead
of being hardcoded; the page <title> gives the current term ("Fall 2026").
"""

import re

from .. import config
from .common import dedupe, strip_tags

CATALOG_URL = config.CATALOG_URL


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
# Academic year / current term
# ---------------------------------------------------------------------------
TERM_TITLE_RE = re.compile(r"<title>\s*(Fall|IAP|Spring|Summer)\s+(\d{4})", re.I)
NOT_OFFERED_RE = re.compile(r'alt="Not offered academic year (\d{4})-(\d{4})"')


def page_term(page_html):
    """'Fall 2026' from the page <title>, or None."""
    m = TERM_TITLE_RE.search(page_html)
    return "%s %s" % (m.group(1).title() if m.group(1).upper() != "IAP" else "IAP", m.group(2)) \
        if m else None


def term_academic_year(term):
    """Academic year a term belongs to: Fall 2026 -> 2026; IAP/Spring/Summer 2027 -> 2026."""
    season, year = term.split()
    return int(year) if season == "Fall" else int(year) - 1


def ay_label(start):
    return "%d-%d" % (start, start + 1)


def detect_years(pages):
    """Work out this/next academic year from the pages.

    The "Not offered academic year X" icons only ever name this year and next year, so they
    define the labels used for offering status. Returns (years dict, problems list); each
    problem is (level, message) with level "fail" or "warn".
    """
    problems = []
    starts = set()
    terms = {}
    for page, h in pages.items():
        for a, b in NOT_OFFERED_RE.findall(h):
            if int(b) != int(a) + 1:
                problems.append(("fail", "%s: odd academic year %s-%s" % (page, a, b)))
            starts.add(int(a))
        t = page_term(h)
        if t:
            terms[page] = t
    distinct_terms = sorted(set(terms.values()))
    term = distinct_terms[0] if len(distinct_terms) == 1 else None
    if len(distinct_terms) > 1:
        problems.append(("warn", "pages show different terms: %s" % ", ".join(distinct_terms)))
    missing = sorted(set(pages) - set(terms))
    if missing:
        problems.append(("warn", "no term in page title: %s" % ", ".join(missing)))

    this = None
    if len(starts) == 2 and max(starts) == min(starts) + 1:
        this = min(starts)
    elif len(starts) == 1 and term:
        only = next(iter(starts))
        this = term_academic_year(term)
        if only not in (this, this + 1):
            problems.append(("fail", "not-offered year %s doesn't fit term %s" %
                             (ay_label(only), term)))
    elif not starts and term:
        this = term_academic_year(term)
        problems.append(("warn", "no 'Not offered' year icons; year taken from title (%s)" % term))
    else:
        problems.append(("fail", "can't tell the academic year (not-offered years: %s)" %
                         (", ".join(ay_label(s) for s in sorted(starts)) or "none")))
    if this is not None and term and term_academic_year(term) != this:
        problems.append(("warn", "title term %s is outside academic year %s (catalog rollover?)"
                         % (term, ay_label(this))))
    years = {
        "term": term,
        "this": ay_label(this) if this is not None else None,
        "next": ay_label(this + 1) if this is not None else None,
    }
    return years, problems


# ---------------------------------------------------------------------------
# Offering status
# ---------------------------------------------------------------------------
def offering_status(body, years):
    notes = []
    this_ay, next_ay = years["this"], years["next"]
    if this_ay and 'alt="Not offered academic year %s"' % this_ay in body:
        status = "Not offered this year (%s)" % this_ay
    elif next_ay and 'alt="Not offered academic year %s"' % next_ay in body:
        status = "Not offered next year (%s)" % next_ay
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


def parse_block(number, body, category, page, department, years, title=None):
    is_grad = 'alt="Graduate"' in body
    if not is_grad:
        return None  # skip undergraduate subjects

    # Title: given by the caller (from the heading), else the <h3> text after the number.
    if title is None:
        mt = re.search(r"<h3[^>]*>\s*" + re.escape(number) + r"\s*(.*?)(?:<br>|</h3>)",
                       body, re.I | re.S)
        title = mt.group(1) if mt else ""
    title = strip_tags(title)

    terms = []
    for t in ("Fall", "IAP", "Spring", "Summer"):
        if 'alt="%s"' % t in body:
            terms.append(t)

    status, notes = offering_status(body, years)

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
        "url": CATALOG_URL.format(page) + "#" + number.split("-")[0],
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


# ---------------------------------------------------------------------------
# Department pages (heading-based identity, range headings)
# ---------------------------------------------------------------------------
NUM = r"[0-9A-Z]+\.[0-9A-Z]+"
HEAD_RE = re.compile(r"<h3[^>]*>\s*(" + NUM + r")(?:\s*-\s*(" + NUM + r"))?\s*(.*?)(?:<br>|</h3>)",
                     re.I | re.S)


def expand_range(first, last):
    """'15.840','15.843' -> ['15.840', ..., '15.843']; 'S' numbers keep their letter and width."""
    pa, sa = first.split(".", 1)
    pb, sb = last.split(".", 1)
    ma, mb = re.fullmatch(r"([A-Z]*)(\d+)", sa), re.fullmatch(r"([A-Z]*)(\d+)", sb)
    if pa != pb or not ma or not mb or ma.group(1) != mb.group(1) or \
            len(ma.group(2)) != len(mb.group(2)):
        return [first, last]
    lo, hi, width = int(ma.group(2)), int(mb.group(2)), len(ma.group(2))
    if hi < lo or hi - lo > 50:
        return [first, last]
    return ["%s.%s%0*d" % (pa, ma.group(1), width, i) for i in range(lo, hi + 1)]


def _blocks(page_html):
    """Yield (position, heading_first, heading_last_or_None, heading_title, body) per block."""
    for m in BLOCK_RE.finditer(page_html):
        body = m.group(2)
        h = HEAD_RE.search(body)
        if not h:
            continue
        yield m.start(), h.group(1), h.group(2), h.group(3), body


def parse_departments(pages, years, own_numbers=()):
    """Graduate subjects on the department pages. `own_numbers` are numbers known to have a
    listing of their own elsewhere (e.g. EECS subject updates) so they leave any range."""
    courses, all_titles, ranges = [], {}, []
    blocks = {}
    own = set(own_numbers)
    for dept in config.CATALOG_DEPARTMENTS:
        for page in dept["pages"]:
            if page not in pages:
                continue  # a missing page is reported by the fetch checks
            blocks[page] = list(_blocks(pages[page]))
            for pos, first, last, title, body in blocks[page]:
                if last:
                    for n in expand_range(first, last):
                        all_titles.setdefault(n, strip_tags(title))
                else:
                    own.add(first)
                    all_titles[first] = strip_tags(title)
    for dept in config.CATALOG_DEPARTMENTS:
        prefix = dept["code"] + "."
        for page in dept["pages"]:
            if page not in blocks:
                continue
            cats = categories_by_pos(pages[page])
            for pos, first, last, title, body in blocks[page]:
                if not first.startswith(prefix):
                    continue  # skip cross-listed subjects from other departments
                cat = category_for(cats, pos)
                range_numbers = None
                number = first
                if last:
                    members = [n for n in expand_range(first, last) if n not in own]
                    ranges.append({"heading": "%s-%s" % (first, last), "page": page,
                                   "rows": members})
                    if not members:
                        continue
                    number = members[0] if len(members) == 1 else \
                        "%s-%s" % (members[0], members[-1])
                    range_numbers = members if len(members) > 1 else None
                rec = parse_block(number, body, cat, page, dept["name"], years, title=title)
                if rec:
                    if range_numbers:
                        rec["range_numbers"] = range_numbers
                    courses.append(rec)
    return courses, all_titles, ranges


# ---------------------------------------------------------------------------
# Common Ground for Computing Education (cross-department "X.C##" subjects)
# ---------------------------------------------------------------------------
# These live on their own catalog page (mCGa) under CG.### anchors, plus a
# "Common Ground" section of m6e. Each block names its real subject number in
# the <h3>. A class can be jointly listed under several departments ("Same
# subject as ..."). Like other joint classes in this dataset, we keep one row per
# covered department; a class with no covered-department number gets one row.
CG_OTHER_DEPT = "Common Ground — other depts"
CG_NUM_RE = re.compile(r"\b[0-9A-Z]+\.[0-9A-Z]+\b")


def parse_common_ground(pages, existing_numbers, years):
    covered = {d["code"]: d["name"] for d in config.CATALOG_DEPARTMENTS}
    seen = set(existing_numbers)
    out = []
    for page, section in config.CG_SOURCES:
        if page not in pages:
            continue
        page_html = pages[page]
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
            rec = parse_block(num, body, category, page, dept, years)
            seen.add(num)
            if prefix not in covered:
                seen.update(joint)
            if not rec:
                continue  # undergraduate
            rec["url"] = CATALOG_URL.format(page) + "#" + anchor
            rec["common_ground"] = True
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def extract(pages, own_numbers=()):
    """pages: {page name: html}. Returns the catalog extract (records + meta + problems)."""
    years, problems = detect_years(pages)
    courses, all_titles, ranges = parse_departments(pages, years, own_numbers)
    cg = parse_common_ground(pages, {c["number"] for c in courses}, years)
    records = courses + cg
    counts = {}
    for r in records:
        counts[r["number"]] = counts.get(r["number"], 0) + 1
    dupes = sorted(n for n, k in counts.items() if k > 1)
    if dupes:
        problems.append(("fail", "duplicate course numbers: %s" % ", ".join(dupes)))
    page_dates = {}
    for page, h in pages.items():
        m = re.search(r"Produced:\s*([^<]+)", h)
        if m:
            page_dates[page] = m.group(1).strip()
    return {
        "years": years,
        "records": records,
        "all_titles": all_titles,
        "ranges": ranges,
        "page_dates": page_dates,
        "problems": problems,
        "counts": {"departments": len(courses), "common_ground": len(cg)},
    }
