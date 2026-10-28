"""MIT Subject Listing index (student.mit.edu/catalog/index.cgi) -> department names.

Maps a subject-number prefix to its department, e.g. "18" -> "Course 18 — Mathematics",
"21M" -> "Course 21M — Music", "HST" -> "HST — Health Sciences and Technology". Used to label
subjects from departments the planner doesn't scrape (e.g. 18.S995 on the EECS updates page).
"""

import re

from .. import config
from .common import strip_tags

_LIST_TAG_RE = re.compile(r"<(?:/?li|/?ul|/?ol)\b[^>]*>", re.I)
_COURSE_RE = re.compile(r"^Course\s+([0-9A-Z]+)\s+-\s+(.+)$")
_CODE_DASH_RE = re.compile(r"^([A-Z][A-Z0-9]*)\s+-\s+(.+)$")
_PAREN_RE = re.compile(r"^(.+?)\s+\(([0-9A-Z]+)\)$")


def parse_entry(text):
    """'Course 6 - EECS...' / 'Music (21M)' / 'HST - Health...' -> (prefix, name) or None."""
    text = re.sub(r"\s+", " ", text).strip()
    for rx, order in ((_COURSE_RE, (1, 2)), (_PAREN_RE, (2, 1)), (_CODE_DASH_RE, (1, 2))):
        m = rx.match(text)
        if m:
            return m.group(order[0]), m.group(order[1]).strip()
    return None


def extract(page_html, page_key="catalog-index/index"):
    records = []
    seen = set()
    # Split on list tags so nested lists ("Course 21 - Humanities" > "Music (21M)") separate.
    for chunk in _LIST_TAG_RE.split(page_html):
        for part in re.split(r"\s*\|\s*", strip_tags(chunk)):
            e = parse_entry(part)
            if e and e[0] not in seen:
                seen.add(e[0])
                records.append({"prefix": e[0], "name": e[1], "_page": page_key})
    problems = []
    if len(records) < 20:
        problems.append(("fail", "catalog index: only %d departments found" % len(records)))
    return {"records": records, "problems": problems}


def department_name(prefix, index_records):
    """Display name for a subject-number prefix, matching the planner's 'Course N — Name'."""
    for d in config.CATALOG_DEPARTMENTS:
        if d["code"] == prefix:
            return d["name"]
    for r in index_records or []:
        if r["prefix"] == prefix:
            lead = "Course %s" % prefix if prefix[0].isdigit() else prefix
            return "%s — %s" % (lead, r["name"])
    return "Course %s" % prefix
