"""Sanity checks that decide whether a scrape run may publish data.

A run fails (and publishes nothing) if any check fails. Count baselines come from the last
*passing* run in runs.jsonl, so a bad run can never lower the bar for the next one.

Checks
  fetch          page returned HTTP 200 and at least MIN_PAGE_BYTES
  login          a public source returned a login / single-sign-on page
  produced       catalog page has a parseable "Produced:" stamp
  stamps_match   all catalog pages carry the same Produced stamp
  page_count     subjects on a page fell more than MAX_DROP below baseline
  page_courses   graduate courses parsed from a page fell more than MAX_DROP below baseline
  page_fields    title/units/description share on a page fell sharply below baseline
  total_courses  parsed graduate courses fell more than MAX_DROP below baseline
  fields         run-wide required fields: every course has a number; title/units/description
                 shares above calibrated floors
  aags_links     AAGS subject links fell more than MAX_DROP below baseline (or zero)
  parse          the parser crashed
  <source>       problems a source parser reports itself (e.g. catalog: academic year can't be
                 determined, duplicate course numbers)

Each check has a level. "fail" blocks publishing. "info" is a note only. "warn" still publishes
but makes the run exit non-zero so it gets noticed (e.g. the catalog title term doesn't match the academic year,
which is expected around the annual rollover).
"""

import re
from urllib.parse import urlparse

from . import config
from .snapshots import produced_stamp

_SUBJECT_RE = re.compile(r"<h3[^>]*>\s*\d+\.[A-Za-z0-9]+", re.I)


class Check:
    def __init__(self, name, scope, ok, detail="", level="fail"):
        self.name = name
        self.scope = scope      # source key ("catalog/m6a") or "run"
        self.ok = ok
        self.detail = detail
        self.level = level      # "fail" blocks publishing; "warn" doesn't

    def to_dict(self):
        d = {"check": self.name, "scope": self.scope, "ok": self.ok, "detail": self.detail}
        if self.level != "fail":
            d["level"] = self.level
        return d

    def __repr__(self):
        return "Check(%s %s %s %s)" % (self.name, self.scope, "ok" if self.ok else "FAIL",
                                       self.detail)


def is_login_page(result):
    host = (urlparse(result.final_url or "").hostname or "").lower()
    if host in config.LOGIN_HOSTS or "touchstone" in host:
        return True
    if result.body[:5] == b"%PDF-":
        return False
    head = result.body[:200000].decode("utf-8", errors="replace").lower()
    return any(m in head for m in config.LOGIN_MARKERS)


def page_metrics(source, result):
    """Observations about one fetched page, independent of the course parser."""
    text = result.text()
    m = {
        "http_status": result.status,
        "bytes": len(result.body),
        "login": bool(result.body) and is_login_page(result),
    }
    if source.kind == "catalog":
        raw, dt = produced_stamp(text)
        m["produced"] = raw
        m["produced_ok"] = dt is not None
        m["subjects"] = len(_SUBJECT_RE.findall(text))
    return m


def course_metrics(courses, aags_count=None):
    """Per-page and run-wide field coverage of parsed graduate courses."""
    by_page = {}
    for c in courses:
        by_page.setdefault(c.get("source_page") or "?", []).append(c)

    def shares(cs):
        n = len(cs) or 1
        return {
            "grad": len(cs),
            "title_share": round(sum(1 for c in cs if c.get("title")) / n, 4),
            "units_share": round(sum(1 for c in cs if c.get("units_total") is not None) / n, 4),
            "desc_share": round(sum(1 for c in cs if c.get("description")) / n, 4),
        }

    out = {"pages": {p: shares(cs) for p, cs in by_page.items()}, "totals": shares(courses)}
    out["totals"]["missing_number"] = sum(1 for c in courses if not c.get("number"))
    if aags_count is not None:
        out["totals"]["aags_links"] = aags_count
    return out


def _drop_check(name, scope, now, base, label):
    if not base:
        return Check(name, scope, now > 0, "%d %s (no baseline yet)" % (now, label))
    floor = base * (1 - config.MAX_DROP)
    pct = (now - base) / base * 100
    return Check(name, scope, now >= floor,
                 "%d %s vs %d baseline (%+.0f%%)" % (now, label, base, pct))


def evaluate(sources, results, pages, courses_info, baseline, parse_error=None):
    """Run every check. Returns a list of Check.

    sources       list of config.Source
    results       {source.key: FetchResult}
    pages         {source.key: page_metrics(...)}
    courses_info  course_metrics(...) or None if parsing never ran
    baseline      last passing run record (dict) or None
    """
    checks = []
    base_pages = (baseline or {}).get("pages", {})
    base_totals = (baseline or {}).get("totals", {})
    catalog_stamps = {}

    for s in sources:
        r, m = results.get(s.key), pages.get(s.key, {})
        if r is None:
            checks.append(Check("fetch", s.key, False, "not fetched"))
            continue
        level = "warn" if getattr(s, "secondary", False) else "fail"
        min_bytes = getattr(s, "min_bytes", config.MIN_PAGE_BYTES)
        fetched = r.status == 200 and len(r.body) >= min_bytes
        detail = "HTTP %s, %.0f KB" % (r.status, len(r.body) / 1024)
        if r.error and r.status != 200:
            detail += " (%s)" % r.error
        elif r.status == 200 and not fetched:
            detail += " (under %d KB)" % (min_bytes // 1024)
        checks.append(Check("fetch", s.key, fetched, detail, level))
        if m.get("login"):
            checks.append(Check("login", s.key, False,
                                "returned a login page (%s)" % r.final_url, level))
            continue
        if not fetched:
            continue
        if s.kind == "catalog":
            checks.append(Check("produced", s.key, m.get("produced_ok", False),
                                m.get("produced") or "no Produced: stamp"))
            if m.get("produced_ok"):
                catalog_stamps[s.key] = m["produced"]
            base = base_pages.get(s.key, {}).get("subjects")
            checks.append(_drop_check("page_count", s.key, m.get("subjects", 0), base,
                                      "subjects"))

    if len(set(catalog_stamps.values())) > 1:
        groups = {}
        for k, v in catalog_stamps.items():
            groups.setdefault(v, []).append(k.split("/")[-1])
        detail = "; ".join("%s: %s" % (v, ", ".join(ps)) for v, ps in sorted(groups.items()))
        checks.append(Check("stamps_match", "run", False, detail))
    elif catalog_stamps:
        checks.append(Check("stamps_match", "run", True,
                            "all %d pages %s" % (len(catalog_stamps),
                                                 next(iter(catalog_stamps.values())))))

    if parse_error:
        checks.append(Check("parse", "run", False, parse_error))
    if courses_info:
        t = courses_info["totals"]
        checks.append(_drop_check("total_courses", "run", t["grad"],
                                  base_totals.get("grad"), "graduate courses"))
        problems = []
        if t.get("missing_number"):
            problems.append("%d without a number" % t["missing_number"])
        for field, floor in (("title_share", config.MIN_TITLE_SHARE),
                             ("units_share", config.MIN_UNITS_SHARE),
                             ("desc_share", config.MIN_DESC_SHARE)):
            if t[field] < floor:
                problems.append("%s %.0f%% < %.0f%%" % (field.split("_")[0], t[field] * 100,
                                                       floor * 100))
        checks.append(Check("fields", "run", not problems, "; ".join(problems) or
                            "title %.0f%%, units %.0f%%, description %.0f%%" %
                            (t["title_share"] * 100, t["units_share"] * 100,
                             t["desc_share"] * 100)))
        # Parsed graduate courses per page: catches a page whose markup changed so the parser
        # finds nothing even though the subject headings are still there.
        for s in sources:
            base = base_pages.get(s.key, {}).get("grad")
            if s.kind == "catalog" and base:
                now = courses_info["pages"].get(s.page, {}).get("grad", 0)
                checks.append(_drop_check("page_courses", s.key, now, base,
                                          "graduate courses parsed"))
        for page, cur in sorted(courses_info["pages"].items()):
            key = "catalog/%s" % page
            base = base_pages.get(key, {})
            drops = []
            for field in ("title_share", "units_share", "desc_share"):
                if field in base and cur[field] < base[field] - config.MAX_FIELD_SHARE_DROP:
                    drops.append("%s %.0f%% (was %.0f%%)" % (field.split("_")[0],
                                                            cur[field] * 100, base[field] * 100))
            if drops:
                checks.append(Check("page_fields", key, False, "; ".join(drops)))
        if "aags_links" in t:
            checks.append(_drop_check("aags_links", "run", t["aags_links"],
                                      base_totals.get("aags_links"), "AAGS subjects"))
    return checks


def problem_checks(source, problems):
    """Turn a source parser's (level, message) problems into checks. "info" notes are shown in
    the summary but never affect the result or exit code."""
    return [Check(source, "run", level == "info", msg, level=level) for level, msg in problems]


def passed(checks):
    """True when nothing blocks publishing (warnings allowed)."""
    return all(c.ok or c.level == "warn" for c in checks)


def run_record(run_id, started_at, finished_at, sources, pages, courses_info, checks,
               published, mode="live", seed=False):
    """The runs.jsonl line for this run. Per-page counts here become future baselines."""
    page_out = {}
    for s in sources:
        m = dict(pages.get(s.key, {}))
        if courses_info and s.kind == "catalog":
            m.update(courses_info["pages"].get(s.page, {}))
        page_out[s.key] = m
    rec = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "mode": mode,
        "status": "seed" if seed else ("pass" if passed(checks) else "fail"),
        "published": published,
        "warnings": sum(1 for c in checks if not c.ok and c.level == "warn"),
        "totals": (courses_info or {}).get("totals", {}),
        "pages": page_out,
        "checks": [c.to_dict() for c in checks],
    }
    return rec


def summary_table(sources, pages, checks, baseline):
    """Human-readable table for the console / CI log."""
    base_pages = (baseline or {}).get("pages", {})
    by_scope = {}
    for c in checks:
        by_scope.setdefault(c.scope, []).append(c)
    lines = ["", "%-26s %5s %7s  %-22s %9s  %s" %
             ("PAGE", "HTTP", "KB", "PRODUCED", "SUBJECTS", "RESULT")]
    for s in sources:
        m = pages.get(s.key, {})
        subj = m.get("subjects")
        base = base_pages.get(s.key, {}).get("subjects")
        subj_txt = "" if subj is None else ("%d" % subj if not base else "%d/%d" % (subj, base))
        fails = [c for c in by_scope.get(s.key, []) if not c.ok]
        lines.append("%-26s %5s %7.0f  %-22s %9s  %s" % (
            s.key, m.get("http_status", "-"), m.get("bytes", 0) / 1024,
            (m.get("produced") or "")[:22], subj_txt,
            ("FAIL " if any(c.level == "fail" for c in fails) else "WARN ") +
            ", ".join(c.name for c in fails) if fails else "ok"))
    lines.append("")
    for c in by_scope.get("run", []):
        mark = "info" if c.level == "info" else (
            "ok" if c.ok else ("WARN" if c.level == "warn" else "FAIL"))
        lines.append("%-4s %-14s %s" % (mark, c.name, c.detail))
    for label, level in (("FAILED CHECKS", "fail"), ("WARNINGS", "warn")):
        bad = [c for c in checks if not c.ok and c.level == level]
        if bad:
            lines.append("")
            lines.append("%s (%d):" % (label, len(bad)))
            for c in bad:
                lines.append("  - %s [%s]: %s" % (c.name, c.scope, c.detail))
    return "\n".join(lines)
