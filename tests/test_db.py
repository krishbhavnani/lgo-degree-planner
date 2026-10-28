import copy
import unittest

from pipeline import db as cdb
from pipeline import identity

YEARS = {"term": "Fall 2026", "this": "2026-2027", "next": "2027-2028"}


def row(number, title="Some Subject", terms=("Fall",), status="Offered", **kw):
    """A published course row, shaped like scrape.build() output."""
    r = {"number": number, "title": title, "department": "Course 15 — Management",
         "category": "Seminars", "terms": list(terms), "offering_status": status,
         "offering_notes": [], "meets_with": [], "same_as": [], "prereq_raw": "",
         "prereq_numbers": [], "units_raw": "3-0-9", "units": {"lec": 3, "lab": 0, "prep": 9},
         "units_total": 12, "units_kind": "fixed", "half_term": None, "date_note": None,
         "schedule": [], "schedule_summary": "Lecture: Mon 10:00–11:00",
         "description": "About %s." % title, "instructor": "A. Teacher",
         "url": "https://x#" + number, "aags": "N/A", "design_approved": None,
         "action_learning": None}
    r.update(kw)
    return r


def ctx(rows, special=(), evals=None, design_rows=(), years=YEARS):
    return {"rows": rows, "special": list(special), "eval_records": evals or {},
            "design_rows": list(design_rows), "years": years}


def run(db, rows, date="2026-10-28", years=YEARS, aliases=(), **kw):
    observed = cdb.observe(ctx(rows, years=years, **kw))
    return cdb.merge(db, observed, "run-" + date, date, years["term"], aliases)


def kinds(changes):
    return sorted({(c["kind"], c.get("field")) for c in changes})


class ObserveTest(unittest.TestCase):
    def test_statuses_this_and_next_year(self):
        obs = cdb.observe(ctx([
            row("15.100", terms=("Fall", "Spring")),
            row("15.200", terms=("Spring",), status="Not offered this year (2026-2027)"),
            row("15.300", terms=("Fall",), status="Not offered next year (2027-2028)"),
            row("15.S50", terms=("Fall",)),
        ]))
        st = lambda cid: {t: o["status"] for t, o in obs[cid]["offerings"].items()}
        self.assertEqual(st("15.100"), {"Fall 2026": "listed", "Spring 2027": "listed",
                                        "Fall 2027": "expected", "Spring 2028": "expected"})
        self.assertEqual(st("15.200"), {"Spring 2027": "not_offered", "Spring 2028": "expected"})
        self.assertEqual(st("15.300"), {"Fall 2026": "listed", "Fall 2027": "not_offered"})
        self.assertEqual(st("15.S50~some-subject"), {"Fall 2026": "listed",
                                                     "Fall 2027": "unverified"})

    def test_schedule_only_on_current_term_and_half_terms(self):
        obs = cdb.observe(ctx([row("15.072", terms=("Fall", "Spring"), date_note="Ends Oct 23"),
                               row("15.005", terms=("Spring",), half_term="H2")]))
        offs = obs["15.072"]["offerings"]
        self.assertEqual(offs["Fall 2026"]["half"], "H1")
        self.assertIsNotNone(offs["Fall 2026"]["schedule_summary"])
        self.assertIsNone(offs["Spring 2027"]["schedule_summary"])
        self.assertIsNone(offs["Fall 2027"]["instructor"])
        self.assertEqual(obs["15.005"]["offerings"]["Spring 2027"]["half"], "H2")

    def test_joint_group_and_clean_title(self):
        obs = cdb.observe(ctx([row("2.739", "[J] Product Design", same_as=["15.783"]),
                               row("15.783", "[J] Product Design", same_as=["2.739"])]))
        self.assertEqual(obs["2.739"]["group"], obs["15.783"]["group"])
        self.assertEqual(obs["2.739"]["title"], "Product Design")

    def test_special_subject_design_needs_matching_title(self):
        rows = [row("2.S988", "Special Subject in Mechanical Engineering",
                    design_approved="approved")]
        design = [{"numbers": ["2.S988"], "name": "Translational Engineering"}]
        obs = cdb.observe(ctx(rows, design_rows=design))
        self.assertNotIn("design", next(iter(obs.values()))["designations"])
        design = [{"numbers": ["2.S988"], "name": "Special Subject in Mechanical Engineering"}]
        obs = cdb.observe(ctx(rows, design_rows=design))
        self.assertIn("design", next(iter(obs.values()))["designations"])

    def test_special_subject_evals_need_matching_title(self):
        rows = [row("15.S04", "Special Seminar in Management"), row("15.100")]
        evals = {"15.S04": {"title": None, "hours_in": 4, "hours_out": 5},
                 "15.100": {"title": None, "hours_in": 3, "hours_out": 6}}
        obs = cdb.observe(ctx(rows, evals=evals))
        self.assertIsNone(obs["15.S04~special-seminar-in-management"]["evals"])
        self.assertEqual(obs["15.100"]["evals"]["hours_in"], 3)

    def test_lab_in_another_term_is_its_own_course(self):
        rows = [row("15.S04", "Generative AI Lab (GENAI-LAB)", terms=("Fall",),
                    catalog_title="Special Seminar in Management", action_learning="GENAI-LAB",
                    al_name="Generative AI Lab", al_term="Spring")]
        obs = cdb.observe(ctx(rows))
        self.assertEqual(sorted(obs), ["15.S04~generative-ai-lab",
                                       "15.S04~special-seminar-in-management"])
        lab = obs["15.S04~generative-ai-lab"]
        self.assertEqual(list(lab["offerings"]), ["Spring 2027"])
        self.assertIn("action_learning", lab["designations"])
        self.assertNotIn("action_learning",
                         obs["15.S04~special-seminar-in-management"]["designations"])

    def test_lab_in_matching_term_keeps_lab_name(self):
        rows = [row("15.S17", "Defense and Dual-Use Ventures Lab (DDUV-LAB)", terms=("Fall",),
                    action_learning="DDUV-LAB", al_name="Defense and Dual-Use Ventures Lab",
                    al_term="Fall")]
        self.assertEqual(list(cdb.observe(ctx(rows))),
                         ["15.S17~defense-and-dual-use-ventures-lab"])

    def test_eecs_special_subject_and_was_alias(self):
        special = [{"numbers": ["6.S978"], "number": "6.S978", "title": "Engineering AI",
                    "term": "Fall 2026", "was": []},
                   {"numbers": ["6.7980"], "number": "6.7980", "title": "Multiagent",
                    "term": "Fall 2026", "was": ["6.S890"]}]
        rows = [row("6.S978", "Engineering AI", is_special=True), row("6.7980", "Multiagent")]
        obs = cdb.observe(ctx(rows, special=special))
        self.assertEqual(list(obs["6.S978~engineering-ai"]["offerings"]), ["Fall 2026"])
        self.assertEqual(obs["6.7980"]["aliases"], ["6.S890"])


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.db = cdb.empty()
        self.rows = [row("15.100", "Strategy", terms=("Fall", "Spring")), row("15.200", "Ops")]
        self.first = run(self.db, self.rows)

    def test_first_run_adds_everything_second_changes_nothing(self):
        self.assertEqual(kinds(self.first), [("course_added", None), ("offering_added", None)])
        self.assertEqual(run(self.db, copy.deepcopy(self.rows), "2026-11-04"), [])
        self.assertEqual(self.db["courses"]["15.100"]["last_seen"], "2026-11-04")
        self.assertEqual(self.db["courses"]["15.100"]["first_seen"], "2026-10-28")

    def test_instructor_change_updates_in_place_with_history(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["instructor"] = "B. New"
        changes = run(self.db, rows, "2026-11-04")
        self.assertEqual({(c["term"], c["field"]) for c in changes},
                         {("Fall 2026", "instructor"), ("Spring 2027", "instructor")})
        off = self.db["courses"]["15.100"]["offerings"]["Fall 2026"]
        self.assertEqual(off["instructor"], "B. New")
        self.assertEqual(off["history"][-1]["old"], "A. Teacher")

    def test_title_and_description_change_same_course(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["title"], rows[0]["description"] = "Strategy II", "New words."
        changes = run(self.db, rows, "2026-11-04")
        self.assertIn(("changed", "title"), kinds(changes))
        self.assertIn(("changed", "description"), kinds(changes))
        self.assertEqual(len(self.db["courses"]), 2)

    def test_course_removed_then_returns(self):
        changes = run(self.db, [self.rows[1]], "2026-11-04")
        c = self.db["courses"]["15.100"]
        self.assertEqual(c["removed"], "2026-11-04")
        self.assertTrue(all(o["status"] == "removed" for o in c["offerings"].values()))
        self.assertIn(("course_removed", None), kinds(changes))
        changes = run(self.db, copy.deepcopy(self.rows), "2026-11-11")
        self.assertNotIn("removed", self.db["courses"]["15.100"])
        self.assertIn(("course_returned", None), kinds(changes))
        self.assertEqual(self.db["courses"]["15.100"]["offerings"]["Fall 2026"]["status"],
                         "listed")

    def test_semester_flip_freezes_past_term(self):
        spring = dict(YEARS, term="Spring 2027")
        run(self.db, [self.rows[1]], "2027-01-20", years=spring)   # 15.100 gone after the flip
        offs = self.db["courses"]["15.100"]["offerings"]
        self.assertEqual(offs["Fall 2026"]["status"], "listed")     # past: frozen
        self.assertEqual(offs["Spring 2027"]["status"], "removed")

    def test_term_dropped_from_listing_is_removed(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["terms"] = ["Fall"]
        changes = run(self.db, rows, "2026-11-04")
        self.assertEqual(self.db["courses"]["15.100"]["offerings"]["Spring 2027"]["status"],
                         "removed")
        self.assertIn(("changed", "status"), kinds(changes))

    def test_special_subject_reused_with_new_topic(self):
        db = cdb.empty()
        run(db, [row("15.S04", "AI Strategy")])
        changes = run(db, [row("15.S04", "Supply Chain Futures")], "2026-11-04")
        self.assertIn("15.S04~ai-strategy", db["courses"])
        self.assertTrue(db["courses"]["15.S04~ai-strategy"].get("removed"))
        self.assertIn("15.S04~supply-chain-futures", db["courses"])
        self.assertIn(("course_added", None), kinds(changes))

    def test_lookalike_renumbering_flagged_then_confirmed(self):
        db = cdb.empty()
        old = row("15.335", "Leading with Impact", description="Students lead projects.")
        run(db, [old])
        new = row("15.703", "Leading with Impact", description="Students lead projects.")
        run(db, [new], "2026-11-04")
        self.assertEqual([(c["old"], c["new"]) for c in db["renumber_candidates"]],
                         [("15.335", "15.703")])
        run(db, [copy.deepcopy(new)], "2026-11-11",
            aliases=[{"old": "15.335", "new": "15.703"}])
        self.assertEqual(db["courses"]["15.703"]["aliases"], ["15.335"])
        self.assertEqual(db["courses"]["15.335"]["renumbered_to"], "15.703")
        self.assertEqual(db["renumber_candidates"], [])

    def test_different_subjects_not_flagged(self):
        db = cdb.empty()
        run(db, [row("15.335", "Leading with Impact")])
        run(db, [row("15.900", "Competitive Strategy")], "2026-11-04")
        self.assertEqual(db["renumber_candidates"], [])


class IdentityTest(unittest.TestCase):
    def test_ids(self):
        self.assertEqual(identity.course_id("6.7980"), "6.7980")
        self.assertEqual(identity.course_id("15.S04", "Generative AI Lab"),
                         "15.S04~generative-ai-lab")
        self.assertEqual(identity.course_id("15.S20-15.S26", "Special Seminar"), "15.S20-15.S26")
        self.assertTrue(identity.titles_match("[J] Machine Learning & Healthcare",
                                              "machine learning and healthcare"))

    def test_half_from_date_note(self):
        self.assertEqual(cdb.half_from_date_note("Ends Oct 23", "Fall"), "H1")
        self.assertEqual(cdb.half_from_date_note("Begins Nov 2", "Fall"), "H2")
        self.assertEqual(cdb.half_from_date_note("Ends Mar 20", "Spring"), "H1")
        self.assertIsNone(cdb.half_from_date_note("Ends Dec 10", "Fall"))


if __name__ == "__main__":
    unittest.main()
