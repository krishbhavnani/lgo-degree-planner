"""EECS subject updates (eecs.mit.edu/academics/subject-updates/) -> special-subjects extract.

The index page links one page per semester ("Subject Updates Fall 2026"); the term is taken
from the link text because the URLs are inconsistent. Each semester page is an empty shell
that loads its content from an eecsis.mit.edu fragment (subj_2027FA.html = Fall 2026), so we
follow index -> semester page -> fragment. Only the current and future terms are followed (no
backfill of past semesters).

Every graduate subject on a fragment is kept, whatever its department (18.S995, 21M.589...).
Headings can carry extra facts kept for later identity work:
    "NEW 6.7980 Topics in Multiagent Learning (was 6.S890)"   -> new, was=[6.S890]
    "6.S974 (also under 2.S988 and 1.S980) Games, ..."         -> also_under=[2.S988, 1.S980]
    "NEW 6.3930/2 AI and Decision Making ..."                   -> numbers=[6.3930, 6.3932]
"""

import re

from .. import config
from .catalog import page_term
from .common import strip_tags

SEASONS = {"IAP": 0, "Spring": 1, "Summer": 2, "Fall": 3}
_LINK_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_TERM_TEXT_RE = re.compile(r"\b(?:Subject Updates?|Subjects? Update|Special Subjects)\s+"
                           r"(Fall|Spring|Summer|IAP)\s+(\d{4})\b", re.I)
_FRAGMENT_RE = re.compile(r"https?://eecsis\.mit\.edu/plugins/(subj_[A-Za-z0-9]+)\.html")
_SECTION_RE = re.compile(r'<h6[^>]*\bid="([^"]+)"[^>]*>(.*?)</h6>(.*?)(?=<h6\b|\Z)', re.I | re.S)
_ROW_RE = re.compile(r"<td[^>]*>\s*([A-Za-z ]+):\s*</td>\s*<td[^>]*>(.*?)</td>", re.I | re.S)
_NUM = r"[0-9A-Z]+\.[0-9A-Z]+"
_HEAD_RE = re.compile(r"^(NEW\s+)?(" + _NUM + r"(?:/[0-9A-Z]+)*)\s*(?:\(also under ([^)]*)\))?\s*"
                      r"(.*?)\s*(?:\(was ([^)]*)\))?$", re.I)


def term_key(term):
    season, year = term.split()
    return (int(year), SEASONS[season])


def norm_term(season, year):
    season = "IAP" if season.upper() == "IAP" else season.title()
    return "%s %s" % (season, year)


def semester_links(index_html):
    """[(term, url)] from the index page, first link per term, in page order."""
    out, seen = [], set()
    for url, text in _LINK_RE.findall(index_html):
        m = _TERM_TEXT_RE.search(strip_tags(text))
        if not m:
            continue
        term = norm_term(m.group(1), m.group(2))
        if term not in seen:
            seen.add(term)
            out.append((term, url))
    return out


def term_page_name(term):
    season, year = term.split()
    return "%s-%s" % (season.lower(), year)


def current_catalog_term(sources, results):
    for s in sources:
        if s.kind == "catalog" and s.key in results and results[s.key].ok:
            t = page_term(results[s.key].text())
            if t:
                return t
    return None


def discover(sources, results):
    """New sources to fetch: semester pages from the index, then fragments from those pages."""
    out = []
    idx = results.get(config.EECS_UPDATES_SOURCE.key)
    current = current_catalog_term(sources, results)
    if not idx or not idx.ok or not current:
        return out
    for term, url in semester_links(idx.text()):
        if term_key(term) < term_key(current):
            continue
        shell = config.Source("eecs-updates", term_page_name(term), url, normalize="html",
                              min_bytes=2048, secondary=True)
        out.append(shell)
        res = results.get(shell.key)
        if res is not None and res.ok:
            m = _FRAGMENT_RE.search(res.text())
            if m:
                out.append(config.Source("eecs-updates", m.group(1), m.group(0),
                                         normalize="html", min_bytes=1024, secondary=True))
    return out


def _expand_numbers(token):
    """'6.3930/2' -> ['6.3930', '6.3932']; '6.S043/6.S983' -> both."""
    parts = token.split("/")
    out = [parts[0]]
    for p in parts[1:]:
        if "." in p:
            out.append(p)
        else:
            out.append(out[0][:-len(p)] + p)
    return out


def parse_fragment(fragment_html, term, page_url, page_key):
    records = []
    for anchor, head, body in _SECTION_RE.findall(fragment_html):
        text = strip_tags(head).replace("§", "").strip()
        m = _HEAD_RE.match(text)
        if not m:
            continue
        fields = {k.strip().lower(): strip_tags(v) for k, v in _ROW_RE.findall(body)}
        desc = re.findall(r'<div[^>]*white-space:\s*pre-line[^>]*>(.*?)</div>', body, re.I | re.S)
        numbers = _expand_numbers(m.group(2).upper())
        records.append({
            "number": "/".join(numbers),
            "numbers": numbers,
            "title": m.group(4).strip(),
            "term": term,
            "level": fields.get("level", ""),
            "units_raw": fields.get("units", "").strip() or None,
            "prereq_raw": fields.get("prereqs", ""),
            "satisfies": fields.get("satisfies", ""),
            "instructors": fields.get("instructors", ""),
            "schedule_raw": fields.get("schedule", ""),
            "description": strip_tags(desc[-1]) if desc else "",
            "new": bool(m.group(1)),
            "was": [n.strip().upper() for n in re.split(r"[/,]| and ", m.group(5) or "")
                    if n.strip()],
            "also_under": re.findall(_NUM, (m.group(3) or "").upper()),
            "url": "%s#%s" % (page_url, anchor),
            "_page": page_key,
        })
    return records


def extract(sources, results):
    """Parse every fetched fragment. Problems are (level, message)."""
    problems, records, terms = [], [], []
    idx = results.get(config.EECS_UPDATES_SOURCE.key)
    if not idx or not idx.ok:
        return {"records": [], "terms": [], "problems": [("fail", "subject-updates index "
                                                                  "not fetched")]}
    links = semester_links(idx.text())
    if not links:
        problems.append(("fail", "no semester links found on the subject-updates index"))
    by_page = {s.page: s for s in sources if s.kind == "eecs-updates"}
    current = current_catalog_term(sources, results)
    for term, url in links:
        shell = by_page.get(term_page_name(term))
        if not shell:
            continue
        res = results.get(shell.key)
        if not res or not res.ok:
            problems.append(("fail", "%s page not fetched" % term))
            continue
        fm = _FRAGMENT_RE.search(res.text())
        if not fm:
            problems.append(("fail", "%s page has no subject list fragment (page layout "
                                     "changed?)" % term))
            continue
        frag = results.get("eecs-updates/%s" % fm.group(1))
        if not frag or not frag.ok:
            problems.append(("fail", "%s fragment %s not fetched" % (term, fm.group(1))))
            continue
        recs = parse_fragment(frag.text(), term, url, "eecs-updates/%s" % fm.group(1))
        if not recs:
            problems.append(("fail", "%s: no subjects found in %s" % (term, fm.group(1))))
        terms.append({"term": term, "page": url, "fragment": fm.group(0),
                      "subjects": len(recs)})
        records += recs
    if current and not any(t["term"] == current for t in terms):
        problems.append(("info", "no subject updates page for %s yet" % current))
    return {"records": records, "terms": terms, "problems": problems}
