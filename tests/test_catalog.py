import json
import os
import shutil
import tempfile
import unittest

from pipeline import config, extracts
from pipeline.sources import aags, catalog


def block(num, title, *, anchors=None, grad=True, extra=""):
    """One catalog subject block, shaped like student.mit.edu/catalog pages."""
    anchors = anchors or [num.split("-")[0]]
    return ("".join('<a name="%s"></a>' % a for a in anchors) +
            "\n<p><h3>%s %s\n<br><img alt=\"______\" src=\"/icns/hr.gif\"></h3>" % (num, title) +
            ('<img alt="Graduate">' if grad else '<img alt="Undergraduate">') +
            ' (<img alt="Spring">)%s<br>Units: 3-0-9<br>' % extra +
            '<img alt="______" src="/icns/hr.gif"><br>About %s.<br><I>A. Teacher</I>'
            "</p><!--end-->\n" % title)


def page(blocks, term="Fall 2026", years=("2026-2027", "2027-2028")):
    icons = "".join('<img alt="Not offered academic year %s">' % y for y in years)
    body = "".join(blocks)
    return ("<html><head><title>%s Course 15: Management</title></head><body>"
            "<h2>Seminars</h2>%s<!--icons %s--></body></html>" % (term, body, icons))


def m15(blocks, **kw):
    return {"m15c": page(blocks, **kw)}


class YearsTest(unittest.TestCase):
    def test_years_from_icons_and_title(self):
        years, problems = catalog.detect_years(m15([]))
        self.assertEqual(years, {"term": "Fall 2026", "this": "2026-2027", "next": "2027-2028"})
        self.assertEqual(problems, [])

    def test_spring_term_same_academic_year(self):
        years, problems = catalog.detect_years(m15([], term="Spring 2027"))
        self.assertEqual(years["this"], "2026-2027")
        self.assertEqual(problems, [])

    def test_rollover_mismatch_is_a_warning(self):
        # Title still says Spring 2027 but the icons already name next year's pair.
        years, problems = catalog.detect_years(
            m15([], term="Spring 2027", years=("2027-2028", "2028-2029")))
        self.assertEqual(years["this"], "2027-2028")
        self.assertEqual([lvl for lvl, _ in problems], ["warn"])

    def test_three_years_fail(self):
        _, problems = catalog.detect_years(
            m15([], years=("2025-2026", "2026-2027", "2027-2028")))
        self.assertIn("fail", [lvl for lvl, _ in problems])

    def test_no_icons_falls_back_to_title_with_warning(self):
        years, problems = catalog.detect_years(m15([], years=()))
        self.assertEqual(years["this"], "2026-2027")
        self.assertEqual([lvl for lvl, _ in problems], ["warn"])

    def test_offering_status_uses_detected_years(self):
        years = {"term": "Fall 2027", "this": "2027-2028", "next": "2028-2029"}
        body = '<img alt="Not offered academic year 2027-2028">'
        self.assertEqual(catalog.offering_status(body, years)[0],
                         "Not offered this year (2027-2028)")


class IdentityTest(unittest.TestCase):
    def test_heading_not_anchor_decides_number(self):
        # The 15.S11 block sits under a 15.S10 anchor (bunched anchors on the real page).
        ex = catalog.extract(m15([
            block("15.S10", "Special Seminar in Management"),
            block("15.S11", "Special Seminar in Management", anchors=["15.S10"]),
            block("15.S10-15.S12", "Special Seminar in Management",
                  anchors=["15.S10", "15.S11", "15.S12"]),
        ]))
        nums = [r["number"] for r in ex["records"]]
        self.assertEqual(nums, ["15.S10", "15.S11", "15.S12"])
        self.assertEqual(ex["problems"], [])

    def test_range_is_one_row_labeled_with_range(self):
        ex = catalog.extract(m15([block("15.840-15.843", "Seminar in Marketing")]))
        (r,) = ex["records"]
        self.assertEqual(r["number"], "15.840-15.843")
        self.assertEqual(r["title"], "Seminar in Marketing")
        self.assertEqual(r["range_numbers"], ["15.840", "15.841", "15.842", "15.843"])
        self.assertEqual(r["url"], config.CATALOG_URL.format("m15c") + "#15.840")

    def test_numbers_with_own_block_leave_the_range(self):
        ex = catalog.extract(m15([
            block("15.579", "Topics in IT"),
            block("15.579-15.580", "Seminar in Information Technology", anchors=["15.580"]),
        ]))
        self.assertEqual([(r["number"], r["title"]) for r in ex["records"]],
                         [("15.579", "Topics in IT"),
                          ("15.580", "Seminar in Information Technology")])

    def test_numbers_listed_elsewhere_leave_the_range(self):
        ex = catalog.extract(m15([block("15.S20-15.S22", "Special Seminar")]),
                             own_numbers={"15.S21"})
        (r,) = ex["records"]
        self.assertEqual(r["range_numbers"], ["15.S20", "15.S22"])

    def test_fully_covered_range_makes_no_row(self):
        ex = catalog.extract(m15([block("15.S10", "A"), block("15.S11", "B"),
                                  block("15.S10-15.S11", "Range", anchors=["15.S10"])]))
        self.assertEqual([r["number"] for r in ex["records"]], ["15.S10", "15.S11"])

    def test_undergraduate_skipped(self):
        ex = catalog.extract(m15([block("15.010", "Undergrad Econ", grad=False)]))
        self.assertEqual(ex["records"], [])
        self.assertEqual(ex["all_titles"]["15.010"], "Undergrad Econ")

    def test_duplicate_numbers_reported_as_failure(self):
        ex = catalog.extract(m15([block("15.S10", "A"), block("15.S10", "B")]))
        self.assertIn("fail", [lvl for lvl, _ in ex["problems"]])

    def test_expand_range(self):
        self.assertEqual(catalog.expand_range("6.S963", "6.S965"),
                         ["6.S963", "6.S964", "6.S965"])
        self.assertEqual(catalog.expand_range("2.S790", "2.S792"),
                         ["2.S790", "2.S791", "2.S792"])
        self.assertEqual(catalog.expand_range("15.5", "16.2"), ["15.5", "16.2"])


class AagsTest(unittest.TestCase):
    def test_link_colors(self):
        html = ('<a style="color:blue;" href="x?search=6.7900">a</a>'
                '<a href="x?search=6.5950" style="color:grey;">b</a>'
                '<a style="color:black;" href="x?search=15.C51">c</a>')
        ex = aags.extract(html)
        self.assertEqual(ex["records"], [
            {"number": "15.C51", "status": "Approved-NotInCatalog"},
            {"number": "6.5950", "status": "Approved-NotThisYear"},
            {"number": "6.7900", "status": "Approved-Offered"},
        ])


class ExtractFileTest(unittest.TestCase):
    def test_records_carry_provenance(self):
        tmp = tempfile.mkdtemp(prefix="lgo-dp-test-")
        try:
            ex = catalog.extract(m15([block("15.840-15.843", "Seminar in Marketing")]))
            src = config.catalog_source("m15c")
            entries = {src.key: {"stored": "snapshots/catalog/m15c/x.html.gz",
                                 "fetched_at": "2026-10-28T02:41:48Z"}}
            written = extracts.write_all(tmp, "run1", [src], entries, {"catalog": ex})
            self.assertEqual(written, ["extracts/catalog.json"])
            with open(os.path.join(tmp, "extracts", "catalog.json"), encoding="utf-8") as f:
                doc = json.load(f)
            rec = doc["records"][0]
            self.assertEqual(rec["_src"], {"page": "catalog/m15c",
                                           "snapshot": "snapshots/catalog/m15c/x.html.gz",
                                           "fetched_at": "2026-10-28T02:41:48Z"})
            self.assertNotIn("eval_hours_in", rec)
            self.assertEqual(doc["years"]["this"], "2026-2027")
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
