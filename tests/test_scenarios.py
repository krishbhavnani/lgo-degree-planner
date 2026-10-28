"""Scenario fixtures: altered copies of the latest real catalog snapshots.

Each test starts from a database built from the unaltered pages, applies one change the real
catalog could make, and checks what the merge does. The pages are read from the archive (the
`data` branch worktree, .data/ by default or $LGO_DP_ARCHIVE); the tests skip without it, so
no MIT pages are committed to the code branch.
"""

import copy
import gzip
import json
import os
import re
import unittest

from pipeline import config, guardrails
from pipeline import db as cdb
from pipeline.sources import catalog

ARCHIVE = os.environ.get("LGO_DP_ARCHIVE", config.ARCHIVE_DIR)


def latest_pages():
    path = os.path.join(ARCHIVE, "manifest.jsonl")
    if not os.path.exists(path):
        return None
    latest = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            snap = e.get("stored") or e.get("unchanged_since")
            if e["source"].startswith("catalog/") and snap:
                latest[e["source"].split("/", 1)[1]] = snap
    pages = {}
    for page in config.catalog_pages():
        if page not in latest:
            return None
        with gzip.open(os.path.join(ARCHIVE, latest[page]), "rb") as f:
            pages[page] = f.read().decode("utf-8", errors="replace")
    return pages


PAGES = latest_pages()
if PAGES:
    # Unchanged pages are archived under their first (older) file, so their Produced stamps
    # differ; give all pages one stamp as a single real fetch would have.
    PAGES = {p: re.sub(r"Produced:\s*[^<]+", "Produced: 27-OCT-2026 05:10 PM", h)
             for p, h in PAGES.items()}


def observe(pages):
    ex = catalog.extract(pages)
    ctx = {"rows": ex["records"], "special": [], "eval_records": {}, "design_rows": [],
           "years": ex["years"]}
    return ex, cdb.observe(ctx)


def block_span(html, number):
    """(start, end) of the catalog block whose heading is `number`."""
    for m in catalog.BLOCK_RE.finditer(html):
        h = catalog.HEAD_RE.search(m.group(2))
        if h and h.group(1) == number and not h.group(2):
            return m.start(), m.end()
    raise AssertionError("block %s not found" % number)


@unittest.skipUnless(PAGES, "no archived catalog snapshots (run from a checkout with .data/)")
class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.pages = copy.deepcopy(PAGES)
        ex, obs = observe(self.pages)
        self.years = ex["years"]
        self.base = ex
        self.db = cdb.empty()
        cdb.merge(self.db, obs, "base", "2026-10-28", self.years["term"])

    def merge(self, pages, date="2026-11-04"):
        ex, obs = observe(pages)
        changes = cdb.merge(self.db, obs, "run", date, ex["years"]["term"])
        return ex, changes

    def pick(self, page, want=lambda r: True):
        """A regular graduate course on `page` matching `want`."""
        for r in self.base["records"]:
            if r["source_page"] == page and re.fullmatch(r"\d+\.\d+", r["number"]) and want(r):
                return r
        self.skipTest("no suitable course on %s" % page)

    def test_course_removed(self):
        r = self.pick("m15a", lambda r: "Fall" in r["terms"])
        a, b = block_span(self.pages["m15a"], r["number"])
        self.pages["m15a"] = self.pages["m15a"][:a] + self.pages["m15a"][b:]
        _, changes = self.merge(self.pages)
        c = self.db["courses"][r["number"]]
        self.assertEqual(c["removed"], "2026-11-04")
        self.assertTrue(all(o["status"] == "removed" for o in c["offerings"].values()))
        self.assertEqual({x["kind"] for x in changes if x["id"] == r["number"]},
                         {"course_removed", "changed"})
        self.assertEqual(len([x for x in changes if x["kind"] == "course_removed"]), 1)

    def test_description_edited(self):
        r = self.pick("m6c", lambda r: r["description"] and r["instructor"])
        a, b = block_span(self.pages["m6c"], r["number"])
        blk = self.pages["m6c"][a:b]
        i = blk.rfind("<I>")
        blk = blk[:i] + " Now includes a lab component. " + blk[i:]
        self.pages["m6c"] = self.pages["m6c"][:a] + blk + self.pages["m6c"][b:]
        _, changes = self.merge(self.pages)
        self.assertEqual([(x["id"], x["field"]) for x in changes],
                         [(r["number"], "description")])
        self.assertIn("lab component", self.db["courses"][r["number"]]["description"])

    def test_instructor_added(self):
        r = self.pick("m15b", lambda r: r["instructor"] and "Fall" in r["terms"])
        a, b = block_span(self.pages["m15b"], r["number"])
        blk = self.pages["m15b"][a:b].replace("</I>", ", Z. Newcomer</I>", 1)
        self.pages["m15b"] = self.pages["m15b"][:a] + blk + self.pages["m15b"][b:]
        _, changes = self.merge(self.pages)
        self.assertTrue(changes)
        self.assertEqual({(x["field"], x["new"].endswith("Z. Newcomer")) for x in changes},
                         {("instructor", True)})
        self.assertTrue(all(x["id"] == r["number"] for x in changes))

    def test_renumbered_course_flagged(self):
        r = self.pick("m2b", lambda r: len(r["description"]) > 80)
        new = "2.%s9" % r["number"].split(".")[1][:2]
        self.assertNotIn(new, {x["number"] for x in self.base["records"]})
        a, b = block_span(self.pages["m2b"], r["number"])
        blk = self.pages["m2b"][a:b].replace(r["number"], new)
        self.pages["m2b"] = self.pages["m2b"][:a] + blk + self.pages["m2b"][b:]
        _, changes = self.merge(self.pages)
        kinds = {(x["id"], x["kind"]) for x in changes if x["kind"].startswith("course_")}
        self.assertEqual(kinds, {(r["number"], "course_removed"), (new, "course_added")})
        self.assertEqual([(c["old"], c["new"]) for c in self.db["renumber_candidates"]],
                         [(r["number"], new)])

    def test_special_subject_reused_with_new_topic(self):
        r = self.pick("m15c", lambda r: True)  # ensure page parsed
        specials = [x for x in self.base["records"] if re.fullmatch(r"15\.S\d\d", x["number"])
                    and x["source_page"] == "m15c"]
        if not specials:
            self.skipTest("no 15.Sxx block on m15c")
        s = specials[-1]
        a, b = block_span(self.pages["m15c"], s["number"])
        blk = re.sub(r"(<h3[^>]*>\s*%s\s*)([^<]*)" % re.escape(s["number"]),
                     r"\1Quantum Finance", self.pages["m15c"][a:b], count=1)
        self.pages["m15c"] = self.pages["m15c"][:a] + blk + self.pages["m15c"][b:]
        _, changes = self.merge(self.pages)
        added = [x["id"] for x in changes if x["kind"] == "course_added"]
        removed = [x["id"] for x in changes if x["kind"] == "course_removed"]
        self.assertEqual(added, ["%s~quantum-finance" % s["number"]])
        self.assertEqual(len(removed), 1)
        self.assertTrue(removed[0].startswith(s["number"] + "~"))

    def test_semester_flip_freezes_fall(self):
        flipped = {p: re.sub(r"<title>\s*Fall\s+2026", "<title>Spring 2027", h)
                   for p, h in self.pages.items()}
        ex, changes = self.merge(flipped, "2027-01-20")
        self.assertEqual(ex["years"]["term"], "Spring 2027")
        self.assertEqual([x for x in changes if x.get("term") == "Fall 2026"], [])
        fall = [c["offerings"]["Fall 2026"] for c in self.db["courses"].values()
                if "Fall 2026" in c["offerings"]]
        self.assertTrue(fall and all(o["status"] != "removed" for o in fall))
        # The listed schedule now belongs to Spring 2027 offerings.
        self.assertTrue(any(x.get("term") == "Spring 2027" and x["field"] == "schedule_summary"
                            for x in changes))

    def test_annual_rollover(self):
        def roll(h):
            h = h.replace("academic year 2027-2028", "academic year 2028-2029")
            h = h.replace("academic year 2026-2027", "academic year 2027-2028")
            return re.sub(r"<title>\s*Fall\s+2026", "<title>Fall 2027", h)
        ex, changes = self.merge({p: roll(h) for p, h in self.pages.items()}, "2027-09-01")
        self.assertEqual(ex["years"], {"term": "Fall 2027", "this": "2027-2028",
                                       "next": "2028-2029"})
        old_terms = {"Fall 2026", "IAP 2027", "Spring 2027", "Summer 2027"}
        self.assertEqual([x for x in changes if x.get("term") in old_terms], [])
        promoted = [x for x in changes if x.get("term") == "Fall 2027" and
                    x["field"] == "status" and x["old"] == "expected" and x["new"] == "listed"]
        self.assertGreater(len(promoted), 50)
        self.assertTrue(any(x["kind"] == "offering_added" and x.get("term") == "Fall 2028"
                            for x in changes))

    def test_broken_html_fails_guardrails(self):
        """Markup change on one page: the parser finds no blocks though headings remain."""
        from pipeline.fetch import FetchResult
        broken = dict(self.pages, m15b=self.pages["m15b"].replace("<!--end-->", ""))
        before = guardrails.course_metrics(self.base["records"])
        after = guardrails.course_metrics(catalog.extract(broken)["records"])
        baseline = {"pages": {"catalog/%s" % p: v for p, v in before["pages"].items()},
                    "totals": before["totals"]}
        srcs = [config.catalog_source(p) for p in config.catalog_pages()]
        results = {s.key: FetchResult(s.url, 200, broken[s.page].encode()) for s in srcs}
        pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in srcs}
        checks = guardrails.evaluate(srcs, results, pages, after, baseline)
        failed = {(c.name, c.scope) for c in checks if not c.ok}
        self.assertEqual(failed, {("page_courses", "catalog/m15b")})
        self.assertFalse(guardrails.passed(checks))

    def test_unaltered_pages_pass_guardrails(self):
        from pipeline.fetch import FetchResult
        m = guardrails.course_metrics(self.base["records"])
        baseline = {"pages": {"catalog/%s" % p: v for p, v in m["pages"].items()},
                    "totals": m["totals"]}
        srcs = [config.catalog_source(p) for p in config.catalog_pages()]
        results = {s.key: FetchResult(s.url, 200, self.pages[s.page].encode()) for s in srcs}
        pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in srcs}
        checks = guardrails.evaluate(srcs, results, pages, m, baseline)
        self.assertTrue(guardrails.passed(checks), [c for c in checks if not c.ok])

if __name__ == "__main__":
    unittest.main()
