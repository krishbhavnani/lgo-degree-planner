import json
import os
import shutil
import tempfile
import unittest

import scrape
from pipeline import config
from pipeline.fetch import FetchResult
from pipeline.sources import action_learning, catalog_index, design, eecs_updates, evals


def ok(body, url="https://example.mit.edu/"):
    return FetchResult(url, 200, body.encode("utf-8") if isinstance(body, str) else body)


class CatalogIndexTest(unittest.TestCase):
    HTML = ("<ul><li><a href='m6a.html'>Course 6 - Electrical Engineering and Computer\n"
            "Science</a></li><li><a href='m21a.html'>Course 21 - Humanities</a><ul>"
            "<li><a href='m21Ma.html'>Music (21M)</a></li>"
            "<li><a href='mCMSa.html'>Comparative Media Studies (CMS)</a> | Writing (21W)</li>"
            "</ul></li><li><a href='mHSTa.html'>HST - Health Sciences and Technology</a></li>"
            "</ul>")

    def test_entries_and_nested_lists(self):
        recs = catalog_index.extract(self.HTML)["records"]
        got = {r["prefix"]: r["name"] for r in recs}
        self.assertEqual(got["21"], "Humanities")
        self.assertEqual(got["21M"], "Music")
        self.assertEqual(got["21W"], "Writing")
        self.assertEqual(got["HST"], "Health Sciences and Technology")
        self.assertEqual(got["6"], "Electrical Engineering and Computer Science")

    def test_department_names(self):
        recs = catalog_index.extract(self.HTML)["records"]
        self.assertEqual(catalog_index.department_name("6", recs), "Course 6 — EECS")
        self.assertEqual(catalog_index.department_name("21M", recs), "Course 21M — Music")
        self.assertEqual(catalog_index.department_name("HST", recs),
                         "HST — Health Sciences and Technology")

    def test_too_few_entries_fails(self):
        self.assertEqual(catalog_index.extract(self.HTML)["problems"][0][0], "fail")


FRAGMENT = """<div class="subj-catalog"><h3> Fall 2026 Subjects </h3>
<h6 class="wp-block-heading" id="6_S978">6.S978 Engineering AI Systems and Agents
<a href="#6_S978">§</a></h6><hr/><table>
<tr valign="top"><td>Level:</td><td style="white-space: pre-line;">Graduate</td><tr>
<tr valign="top"><td>Units:</td><td style="white-space: pre-line;">2-0-10 </td><tr>
<tr valign="top"><td>Prereqs:</td><td style="white-space: pre-line;">6.3900</td><tr>
<tr valign="top"><td>Satisfies:</td><td style="white-space: pre-line;">AUS, AAGS in Artificial Intelligence</td><tr>
<tr valign="top"><td>Instructors:</td><td style="white-space: pre-line;">Omar Khattab (EECS)</td><tr>
<tr valign="top"><td>Schedule:</td><td style="white-space: pre-line;">W11-1, room 32-144</td><tr>
</table><hr/><div style="white-space: pre-line;">Builds AI systems.</div>
<h6 id="NEW_6_7980">NEW 6.7980 Topics in Multiagent Learning (was 6.S890)
<a href="#NEW_6_7980">§</a></h6><table><tr><td>Level:</td><td>Graduate</td><tr></table>
<h6 id="NEW_6_3930_2">NEW 6.3930/2  AI in Medicine (was 6.S043/6.S983)</h6>
<table><tr><td>Level:</td><td>Undergraduate and Graduate</td><tr></table>
<h6 id="x">6.S974 (also under 2.S988 and 1.S980) Games, Learning, and Security</h6>
<table><tr><td>Level:</td><td>Graduate</td><tr></table>
<h6 id="y">6.S057 Verified Software Engineering</h6>
<table><tr><td>Level:</td><td>Undergraduate</td><tr></table></div>"""

INDEX = """<a href="https://www.eecs.mit.edu/academics/subject-updates/subject-updates-fall-2026/">Subject Updates Fall 2026</a>
<a href="https://www.eecs.mit.edu/academics/subject-updates/subjects-update-fall-2025/">Subject Updates Fall 2025</a>
<a href="https://www.eecs.mit.edu/?page_id=8193">Subject Updates Spring 2025</a>
<a href="https://www.eecs.mit.edu/academics/subject-updates/subject-updates-fall-2026/">Subject Updates Fall 2026</a>
<a href="/x">Changes to 6.1903/6.1904</a>"""

SHELL = ('<div id="requirements"></div><script>xhr.open("GET", '
         '"https://eecsis.mit.edu/plugins/subj_2027FA.html?ts=" + Date.now(), true);</script>')


class EecsUpdatesTest(unittest.TestCase):
    def test_semester_links_from_link_text(self):
        links = eecs_updates.semester_links(INDEX)
        self.assertEqual([t for t, _ in links], ["Fall 2026", "Fall 2025", "Spring 2025"])
        self.assertEqual(links[2][1], "https://www.eecs.mit.edu/?page_id=8193")

    def test_parse_fragment(self):
        recs = {r["number"]: r for r in eecs_updates.parse_fragment(
            FRAGMENT, "Fall 2026", "https://u/fall", "eecs-updates/subj_2027FA")}
        r = recs["6.S978"]
        self.assertEqual((r["title"], r["level"], r["units_raw"]),
                         ("Engineering AI Systems and Agents", "Graduate", "2-0-10"))
        self.assertEqual(r["instructors"], "Omar Khattab (EECS)")
        self.assertEqual(r["description"], "Builds AI systems.")
        self.assertEqual(r["url"], "https://u/fall#6_S978")
        self.assertEqual(recs["6.7980"]["was"], ["6.S890"])
        self.assertTrue(recs["6.7980"]["new"])
        self.assertEqual(recs["6.3930/6.3932"]["numbers"], ["6.3930", "6.3932"])
        self.assertEqual(recs["6.3930/6.3932"]["was"], ["6.S043", "6.S983"])
        self.assertEqual(recs["6.S974"]["also_under"], ["2.S988", "1.S980"])
        self.assertEqual(recs["6.S974"]["title"], "Games, Learning, and Security")

    def _run(self, catalog_term="Fall 2026"):
        cat = config.catalog_source("m6a")
        sources = [cat, config.EECS_UPDATES_SOURCE]
        results = {cat.key: ok("<title>%s Course 6</title>" % catalog_term),
                   config.EECS_UPDATES_SOURCE.key: ok(INDEX)}
        new = eecs_updates.discover(sources, results)
        return sources, results, new

    def test_discover_skips_past_terms_then_finds_fragment(self):
        sources, results, new = self._run()
        self.assertEqual([s.key for s in new], ["eecs-updates/fall-2026"])
        results[new[0].key] = ok(SHELL)
        sources += new
        new2 = eecs_updates.discover(sources, results)
        self.assertEqual([s.key for s in new2], ["eecs-updates/fall-2026",
                                                 "eecs-updates/subj_2027FA"])
        self.assertEqual(new2[1].url, "https://eecsis.mit.edu/plugins/subj_2027FA.html")
        results[new2[1].key] = ok(FRAGMENT)
        sources.append(new2[1])
        ex = eecs_updates.extract(sources, results)
        self.assertEqual(ex["problems"], [])
        self.assertEqual(len(ex["records"]), 5)

    def test_missing_fragment_is_a_failure(self):
        sources, results, new = self._run()
        results[new[0].key] = ok("<p>redesigned page, no fragment</p>")
        ex = eecs_updates.extract(sources + new, results)
        self.assertEqual(ex["problems"][0][0], "fail")

    def test_no_page_for_current_term_is_info(self):
        sources, results, new = self._run(catalog_term="Spring 2027")
        self.assertEqual(new, [])
        ex = eecs_updates.extract(sources, results)
        self.assertEqual(ex["problems"], [("info", "no subject updates page for Spring 2027 yet")])


DESIGN_HTML = """<table><tr><th>Course #</th><th>Name</th><th>Units</th></tr>
<tr><td>1.C51/6.C51</td><td>ML for Sustainable Systems</td><td>12</td></tr>
<tr><td>2.739J/15.783J</td><td>Product Design</td><td>12</td></tr>
<tr><td>*2.S988</td><td>Translational Engineering</td><td>12</td></tr>
<tr><td>2.98+</td><td>Sports Technology</td><td>6+6</td></tr>
<tr><td>2.s789</td><td>Advanced Manufacturing</td><td>12</td></tr>
<tr><td>2.832</td><td>Carbon Neutrality</td><td>12</td></tr></table>
<p>Design Classes with Conditional Approval</p>
<table><tr><th>Course #</th><th>Name</th></tr>
<tr><td>2.832</td><td>Carbon Neutrality</td></tr>
<tr><td>SCM.C51/6.C51</td><td>ML for Supply Chain</td></tr>
<tr><td>HST.956 / 6.793</td><td>Machine Learning for Healthcare</td></tr></table>"""

CATALOG = [{"number": n, "title": t} for n, t in [
    ("6.C51", "Modeling with ML"), ("1.C51", "ML for Sustainable Systems"),
    ("SCM.C51", "ML for Supply Chain"), ("2.739", "[J] Product Design"),
    ("15.783", "[J] Product Design"), ("2.S988", "Special Subject"), ("2.98", "Sports Tech"),
    ("2.832", "Carbon Neutrality"), ("6.7930", "[J] Machine Learning for Healthcare")]]


class DesignTest(unittest.TestCase):
    def test_numbers_in(self):
        self.assertEqual(design.numbers_in("2.739J/15.783J"), ["2.739", "15.783"])
        self.assertEqual(design.numbers_in("*2.S988"), ["2.S988"])
        self.assertEqual(design.numbers_in("2.98+"), ["2.98"])
        self.assertEqual(design.numbers_in("2.s789"), ["2.S789"])
        self.assertEqual(design.numbers_in("HST.956 / 6.793"), ["HST.956", "6.793"])
        self.assertEqual(design.numbers_in("10.547J/7.547J/15.136J"),
                         ["10.547", "7.547", "15.136"])

    def test_extract_markers(self):
        ex = design.extract(DESIGN_HTML)
        self.assertEqual(ex["problems"], [])
        by_raw = {r["raw"]: r for r in ex["records"]}
        self.assertEqual(by_raw["*2.S988"]["markers"], "*")
        self.assertEqual(by_raw["2.98+"]["units"], "6+6")
        self.assertEqual(sum(1 for r in ex["records"] if r["status"] == "conditional"), 3)

    def test_header_change_fails(self):
        ex = design.extract(DESIGN_HTML.replace("<th>Course #</th>", "<th>Subject</th>", 1))
        self.assertIn("fail", [p[0] for p in ex["problems"]])

    def test_resolve(self):
        status, notes = design.resolve(design.extract(DESIGN_HTML)["records"], CATALOG)
        self.assertEqual(status["2.739"], "approved")
        self.assertEqual(status["15.783"], "approved")
        self.assertEqual(status["2.832"], "conditional")          # in both lists
        self.assertEqual(status["6.C51"], "approved")              # shared Common Ground core
        self.assertEqual(status["SCM.C51"], "conditional")
        self.assertEqual(status["6.7930"], "conditional")          # old number, by title
        self.assertTrue(any("matched 6.7930 by title" in n for n in notes))
        self.assertTrue(any("2.s789" in n for n in notes))         # covered dept, not found


def label(x, y, text, size=28.0):
    return (x, y, text, size)


class ActionLearningTest(unittest.TestCase):
    def test_booklet_link_prefers_newest(self):
        html = ('<a href="//mitsloan.mit.edu/files/AL-CourseBooklet%20Fall%202025.pdf">old</a>'
                '<a href="/files/AL-CourseBooklet%20Fall%202026%20updates.pdf">new</a>'
                '<a href="/files/annual-report-2027.pdf">report</a>')
        self.assertEqual(action_learning.booklet_link(html),
                         "https://mitsloan.mit.edu/files/AL-CourseBooklet%20Fall%202026%20"
                         "updates.pdf")

    def test_parse_page_pairs_labels_and_numbers(self):
        frags = [
            (27, 570, "15.451", 10.0), label(169, 568, "INVESTMENT", 22.0),
            label(169, 541, "MANAGEMENT LAB", 22.0), (169, 516, "INVESTMENT MANAGEMENT LAB", 10.0),
            (166, 365, "TERM", 9.0), (199, 365, "FALL", 10.0),
            (741, 569, "15.830", 10.0), label(440, 562, "EM-LAB"),
            (440, 542, "ENTERPRISE MANAGEMENT LAB", 10.0),
            (442, 352, "TERM", 9.0), (474, 352, "FALL+IAP", 10.0),
            (27, 277, "15.401 or equivalent", 11.0),
        ]
        labs = action_learning.parse_page(frags)
        self.assertEqual([(l["number"], l["label"], l["code"], l["name"], l["term"]) for l in labs], [
            ("15.451", "INVESTMENT MANAGEMENT LAB", None, "Investment Management Lab", "FALL"),
            ("15.830", "EM-LAB", "EM-LAB", "Enterprise Management Lab", "FALL+IAP")])

    def test_unpositioned_number_falls_back_to_text_order(self):
        frags = [(27, 569, "15.S24 SSIM", 10.0), label(166, 562, "LWI"),
                 label(441, 558, "FIN-LAB"), (0, 0, "15.453", 1.0)]
        labs = action_learning.parse_page(frags, "15.S24 SSIM      LWI      FIN-LAB    15.453")
        self.assertEqual([(l["number"], l["label"]) for l in labs],
                         [("15.S24", "LWI"), ("15.453", "FIN-LAB")])

    def test_section_header_without_number_dropped(self):
        frags = [label(169, 563, "EXECUTIVE"), label(169, 529, "LABS"),
                 (27, 483, "15.708", 10.0), label(169, 481, "GO-LAB", 14.0)]
        labs = action_learning.parse_page(frags)
        self.assertEqual([l["number"] for l in labs], ["15.708"])

    def test_nice_title(self):
        self.assertEqual(action_learning.nice_title("GENERATIVE AI LAB"), "Generative AI Lab")
        self.assertEqual(action_learning.nice_title("DEFENSE AND DUAL-USE VENTURES LAB"),
                         "Defense and Dual-Use Ventures Lab")

    def _al(self, booklets, designations=None, names=()):
        return {"booklets": booklets, "designations": designations or {},
                "labs_page_names": list(names)}

    def lab(self, number, code, name, term="FALL"):
        return {"number": number, "code": code, "label": code, "name": name, "term": term}

    def test_resolve_confirmed_and_title_fallback(self):
        cat = [{"number": "15.572", "title": "Analytics Lab"},
               {"number": "15.335", "title": "Leading with Impact: A Social Impact Lab"},
               {"number": "15.S20-15.S26", "title": "Special Seminar in Management"}]
        al = self._al({"2026-2027": {"labs": [
            self.lab("15.572", "A-LAB", "Analytics Lab"),
            self.lab("15.S24", "LWI", "Leading with Impact: A Social Impact Lab", "IAP")]}},
            names=["Analytics Lab", "Leading with Impact: A Social Impact Lab", "Asia Lab"])
        out, notes = action_learning.resolve(al, cat, "2026-2027")
        self.assertEqual(out["15.572"]["status"], "confirmed")
        self.assertEqual(out["15.335"]["booklet_number"], "15.S24")
        self.assertTrue(any("'Asia Lab'" in n for n in notes))
        self.assertEqual(set(al["designations"]), {"15.572", "15.335"})

    def test_late_booklet_carries_regular_labs_and_flags_special_subjects(self):
        prev = {"15.572": {"code": "A-LAB", "catalog_title": "Analytics Lab",
                           "booklet_year": "2026-2027", "status": "confirmed"},
                "15.399": {"code": "E-LAB", "catalog_title": "Entrepreneurship Lab",
                           "booklet_year": "2026-2027", "status": "confirmed"},
                "15.S04": {"code": "GENAI-LAB", "catalog_title": "Special Seminar",
                           "booklet_year": "2026-2027", "status": "confirmed"}}
        cat = [{"number": "15.572", "title": "Analytics Lab"},
               {"number": "15.399", "title": "Entrepreneurship Lab: Renamed"},
               {"number": "15.S04", "title": "Special Seminar"}]
        al = self._al({"2026-2027": {"labs": []}}, prev)
        out, notes = action_learning.resolve(al, cat, "2027-2028")
        self.assertEqual(out["15.572"]["status"], "carried")
        self.assertNotIn("15.399", out)                       # title changed -> dropped
        self.assertEqual(out["15.S04"]["status"], "unconfirmed")
        self.assertTrue(any("no 2027-2028 booklet yet" in n for n in notes))

    def test_extract_keeps_earlier_booklets_when_pdf_missing(self):
        prev = self._al({"2025-2026": {"labs": [self.lab("15.572", "A-LAB", "x")]}})
        ex = action_learning.extract([], {}, prev)
        self.assertIn("2025-2026", ex["booklets"])
        self.assertEqual(ex["problems"][0][0], "fail")


class EvalsTest(unittest.TestCase):
    def test_legacy_file(self):
        tmp = tempfile.mkdtemp(prefix="lgo-dp-test-")
        try:
            path = os.path.join(tmp, "evals.json")
            with open(path, "w") as f:
                json.dump({"6.5060": {"eval_status": "ok", "eval_hours_in": 3.5,
                                      "eval_hours_out": 10, "eval_term": "Fall 2025"},
                           "15.S04": {"eval_status": "ok", "eval_hours_in": 4}}, f)
            ex, problems = evals.load(path)
            recs = {r["number"]: r for r in ex["records"]}
            self.assertEqual(recs["6.5060"]["hours_in"], 3.5)
            self.assertIsNone(recs["6.5060"]["title"])
            self.assertEqual(evals.legacy_fields(recs["6.5060"])["eval_hours_out"], 10)
            self.assertEqual(problems[0][0], "info")
        finally:
            shutil.rmtree(tmp)


class PublishHelpersTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(scrape._units("3–0–9")[2], 12)
        self.assertEqual(scrape._units("3 - 0 - 9")[0], "3-0-9")
        self.assertEqual(scrape._units("12 units (3-1.5-7.5)")[1]["lab"], 1.5)
        self.assertEqual(scrape._units("12")[2], 12)
        self.assertEqual(scrape._units(None)[2], None)

    def test_pretty_schedule(self):
        self.assertEqual(scrape.pretty_schedule("W11-1, room 32-144"),
                         "Lecture: Wed 11:00–13:00 (32-144)")
        self.assertEqual(scrape.pretty_schedule("W7-10pm, room 36-144"),
                         "Lecture: Wed 19:00–22:00 (36-144)")
        self.assertEqual(scrape.pretty_schedule("Thursdays 1-2:30"), "Thursdays 1-2:30")

    def test_clean_instructors_and_area(self):
        self.assertEqual(scrape.clean_instructors("Nir N. Shavit (EECS) Alex Matveev (Outside)"),
                         "Nir N. Shavit, Alex Matveev")
        self.assertEqual(scrape.research_area("AUS, AAGS in Theoretical Computer Science",
                                              ["Machine Learning", "Theoretical Computer Science"]),
                         "Theoretical Computer Science")
        self.assertEqual(scrape.research_area("", ["Vision"]), "Special Subject")

    def test_lab_code(self):
        self.assertEqual(scrape.lab_code({"code": "A-LAB"}), "A-LAB")
        self.assertEqual(scrape.lab_code({"code": "ASEAN LAB"}), "ASEAN LAB")
        self.assertEqual(scrape.lab_code({"code": "INVESTMENT MANAGEMENT LAB"}), "IM-LAB")


class SecondaryFallbackTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lgo-dp-test-")
        os.makedirs(os.path.join(self.dir, "extracts"))
        with open(os.path.join(self.dir, "extracts", "design.json"), "w") as f:
            json.dump({"run_id": "r0", "records": [{"numbers": ["2.832"]}] * 10}, f)
        self.src = config.DESIGN_SOURCE

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_secondary(self, fresh, fetched=True):
        results = {self.src.key: ok("x" * 30000)} if fetched else {}
        return scrape.secondary("design", "design", [self.src], results, lambda last: fresh,
                                self.dir)

    def test_good_extract_used(self):
        fresh = {"records": [{"numbers": ["2.120"]}] * 10, "problems": []}
        ex = self.run_secondary(fresh)
        self.assertIs(ex, fresh)

    def test_parser_failure_keeps_last_good_with_warning(self):
        ex = self.run_secondary({"records": [], "problems": [("fail", "header changed")]})
        self.assertTrue(ex["_fallback"])
        self.assertEqual(ex["problems"][0][0], "warn")
        self.assertIn("header changed", ex["problems"][0][1])

    def test_fetch_failure_keeps_last_good(self):
        ex = self.run_secondary({"records": [{"numbers": ["x"]}] * 10, "problems": []},
                                fetched=False)
        self.assertTrue(ex["_fallback"])

    def test_big_drop_keeps_last_good(self):
        ex = self.run_secondary({"records": [{"numbers": ["x"]}] * 3, "problems": []})
        self.assertTrue(ex["_fallback"])
        self.assertIn("dropped from 10 to 3", ex["problems"][0][1])

    def test_no_earlier_extract_fails(self):
        os.remove(os.path.join(self.dir, "extracts", "design.json"))
        ex = self.run_secondary({"records": [], "problems": [("fail", "header changed")]})
        self.assertEqual(ex["problems"][0][0], "fail")


if __name__ == "__main__":
    unittest.main()
