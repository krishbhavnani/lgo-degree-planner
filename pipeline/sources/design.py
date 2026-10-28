"""LGO handbook, Appendix 2: pre-approved design classes -> design extract.

Two tables: approved (Course # / Name / Units) and conditional (Course # / Name). The page has
no date, so changes are detected by the snapshot diff. Course-number cells are messy:
    joint numbers   "2.739J/15.783J", "HST.956 / 6.793"
    markers         "*2.S988" (unexplained on the page), "2.98+" (needs extra 6-unit credit)
    case            "2.s789"
    old EECS        "6.793" (now 6.7930), "6.811" (now 6.8110)

resolve() maps rows to catalog rows: an exact number match first; otherwise the row name
matched against catalog titles (this is how pre-2022 EECS numbers resolve). If a course is in
both lists, conditional wins, except for the shared core of a Common Ground pairing: the
approved table pairs 6.C51 with 1.C51/2.C51 and the conditional table pairs it with SCM.C51,
so only the SCM.C51 module becomes conditional and 6.C51 stays approved.
"""

import re

from .. import config
from .common import strip_tags

_TABLE_RE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_NUM_RE = re.compile(r"[0-9A-Z]+\.[0-9A-Z]+")


def numbers_in(cell):
    """'2.739J/15.783J' -> ['2.739', '15.783']; '*2.S988' -> ['2.S988']; '2.s789' -> ['2.S789']."""
    out = []
    for tok in re.split(r"[/,\s]+", cell.upper()):
        tok = tok.strip("*+")
        m = _NUM_RE.fullmatch(tok)
        if not m:
            continue
        n = re.sub(r"J$", "", tok) if re.search(r"\d+J$", tok) else tok
        if n not in out:
            out.append(n)
    return out


def _rows(table_html):
    rows = []
    for tr in _ROW_RE.findall(table_html):
        rows.append([strip_tags(c) for c in _CELL_RE.findall(tr)])
    return rows


def extract(page_html, page_key="design/appendix-2"):
    problems = []
    tables = [_rows(t) for t in _TABLE_RE.findall(page_html)]
    expect = [("approved", ["Course #", "Name", "Units"]), ("conditional", ["Course #", "Name"])]
    records = []
    if len(tables) != 2:
        problems.append(("fail", "expected 2 tables (approved, conditional), found %d" %
                         len(tables)))
    for (status, header), rows in zip(expect, tables):
        if not rows or [h.strip() for h in rows[0]] != header:
            problems.append(("fail", "%s table header changed: %s" %
                             (status, rows[0] if rows else "empty")))
            continue
        for cells in rows[1:]:
            if not cells or not cells[0].strip():
                continue
            raw = cells[0].strip()
            nums = numbers_in(raw)
            if not nums:
                problems.append(("warn", "design %s row with no course number: %r" %
                                 (status, raw)))
                continue
            records.append({
                "status": status,
                "raw": raw,
                "numbers": nums,
                "name": cells[1].strip() if len(cells) > 1 else "",
                "units": cells[2].strip() if len(cells) > 2 else None,
                "markers": "".join(sorted(set(re.findall(r"[*+]", raw)))) or None,
                "_page": page_key,
            })
    if not any(r["status"] == "approved" for r in records):
        problems.append(("fail", "no approved design classes found"))
    return {"records": records, "problems": problems}


def _norm_title(t):
    t = re.sub(r"^\[J\]\s*", "", t or "")
    t = t.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def resolve(design_records, catalog_records):
    """Return ({catalog number: "approved"|"conditional"}, notes).

    notes lists rows naming a covered-department number that matched nothing (worth a look);
    rows only from departments the planner doesn't scrape are ignored silently.
    """
    by_num = {r["number"]: r for r in catalog_records}
    by_title = {}
    for r in catalog_records:
        by_title.setdefault(_norm_title(r.get("title")), []).append(r["number"])
    covered = {d["code"] for d in config.CATALOG_DEPARTMENTS}
    approved_anywhere = set()
    status, notes = {}, []
    for row in design_records:
        hits = [n for n in row["numbers"] if n in by_num]
        how = "number"
        if not hits:
            hits = by_title.get(_norm_title(row["name"]), [])
            how = "title"
        if not hits:
            if any(n.split(".")[0] in covered for n in row["numbers"]):
                notes.append("%s %r (%s) matched no catalog course" %
                             (row["status"], row["raw"], row["name"]))
            continue
        pairing = len(row["numbers"]) > 1 and all(
            re.fullmatch(r"[0-9A-Z]+\.C\d+", n) for n in row["numbers"])
        for n in hits:
            if row["status"] == "approved":
                approved_anywhere.add(n)
                if status.get(n) != "conditional":
                    status[n] = "approved"
            elif pairing and n in approved_anywhere:
                continue  # shared Common Ground core approved through another pairing
            else:
                status[n] = "conditional"
        if how == "title":
            notes.append("%s %r matched %s by title" % (row["status"], row["raw"],
                                                        ", ".join(hits)))
    return status, notes
