import unittest

from pipeline import guardrails
from tests import fixtures as fx

M6A, M6B, AAGS = fx.SOURCES
AAGS_BODY = b"<html>" + b"x" * 30000 + b"</html>"


def run(bodies=None, courses=None, aags_links=190, baseline=None, results=None,
        parse_error=None):
    """Evaluate a synthetic run. Defaults are a healthy run."""
    bodies = bodies or {}
    results = results or {}
    for s in fx.SOURCES:
        if s.key not in results:
            body = bodies.get(s.key, AAGS_BODY if s.kind == "aags" else fx.catalog_html())
            results[s.key] = fx.result(body, url=s.url)
    pages = {s.key: guardrails.page_metrics(s, results[s.key]) for s in fx.SOURCES}
    if courses is None:
        courses = fx.courses(40, "m6a") + fx.courses(40, "m6b")
    info = guardrails.course_metrics(courses, aags_links) if parse_error is None else None
    checks = guardrails.evaluate(fx.SOURCES, results, pages, info, baseline, parse_error)
    return checks, pages, info


def failed(checks):
    return {(c.name, c.scope) for c in checks if not c.ok}


def baseline_from(checks, pages, info):
    return guardrails.run_record("b", "", "", fx.SOURCES, pages, info, checks, True)


class GuardrailsTest(unittest.TestCase):
    def setUp(self):
        checks, pages, info = run()
        self.assertTrue(guardrails.passed(checks), checks)
        self.baseline = baseline_from(checks, pages, info)
        self.assertEqual(self.baseline["status"], "pass")

    def test_good_run_passes_against_baseline(self):
        checks, _, _ = run(baseline=self.baseline)
        self.assertTrue(guardrails.passed(checks), [c for c in checks if not c.ok])

    def test_small_drop_ok(self):
        checks, _, _ = run(bodies={M6A.key: fx.catalog_html(n_subjects=32)},
                           baseline=self.baseline)
        self.assertTrue(guardrails.passed(checks))

    def test_page_drop_over_30_percent_fails(self):
        checks, _, _ = run(bodies={M6A.key: fx.catalog_html(n_subjects=24)},
                           baseline=self.baseline)
        self.assertIn(("page_count", M6A.key), failed(checks))

    def test_total_courses_drop_fails(self):
        checks, _, _ = run(courses=fx.courses(25, "m6a") + fx.courses(23, "m6b"),
                           baseline=self.baseline)
        self.assertIn(("total_courses", "run"), failed(checks))

    def test_aags_drop_fails(self):
        checks, _, _ = run(aags_links=120, baseline=self.baseline)
        self.assertIn(("aags_links", "run"), failed(checks))

    def test_aags_zero_fails_without_baseline(self):
        checks, _, _ = run(aags_links=0)
        self.assertIn(("aags_links", "run"), failed(checks))

    def test_mismatched_stamps_fail(self):
        checks, _, _ = run(bodies={M6B.key: fx.catalog_html(produced="26-OCT-2026 05:10 PM")})
        self.assertIn(("stamps_match", "run"), failed(checks))

    def test_missing_stamp_fails(self):
        body = fx.catalog_html().replace(b"Produced:", b"Generated:")
        checks, _, _ = run(bodies={M6A.key: body})
        self.assertIn(("produced", M6A.key), failed(checks))

    def test_unparseable_stamp_fails(self):
        checks, _, _ = run(bodies={M6A.key: fx.catalog_html(produced="TBD")})
        self.assertIn(("produced", M6A.key), failed(checks))

    def test_truncated_page_fails(self):
        checks, _, _ = run(bodies={M6A.key: fx.catalog_html()[:5000]})
        self.assertIn(("fetch", M6A.key), failed(checks))

    def test_http_error_fails(self):
        res = fx.result(b"oops", url=M6A.url, status=503)
        res.error = "HTTP 503"
        checks, _, _ = run(results={M6A.key: res})
        self.assertIn(("fetch", M6A.key), failed(checks))

    def test_login_page_fails(self):
        res = fx.result(fx.login_html(), url=M6A.url,
                        final_url="https://idp.mit.edu/idp/profile/SAML2/Redirect/SSO")
        checks, pages, _ = run(results={M6A.key: res})
        self.assertTrue(pages[M6A.key]["login"])
        self.assertIn(("login", M6A.key), failed(checks))

    def test_login_markers_without_redirect_fail(self):
        res = fx.result(fx.login_html(), url=M6A.url)
        checks, _, _ = run(results={M6A.key: res})
        self.assertIn(("login", M6A.key), failed(checks))

    def test_missing_titles_fail(self):
        checks, _, _ = run(courses=fx.courses(40, "m6a", titled=0.5) + fx.courses(40, "m6b"))
        self.assertIn(("fields", "run"), failed(checks))

    def test_missing_units_fail(self):
        checks, _, _ = run(courses=fx.courses(40, "m6a", with_units=0.3) +
                           fx.courses(40, "m6b", with_units=0.3))
        self.assertIn(("fields", "run"), failed(checks))

    def test_page_field_share_drop_fails(self):
        checks, _, _ = run(courses=fx.courses(40, "m6a", with_units=0.6) + fx.courses(40, "m6b"),
                           baseline=self.baseline)
        self.assertIn(("page_fields", M6A.key), failed(checks))

    def test_parse_error_fails(self):
        checks, _, _ = run(parse_error="AttributeError: boom")
        self.assertIn(("parse", "run"), failed(checks))

    def test_failed_run_record_marked_fail(self):
        checks, pages, info = run(bodies={M6A.key: fx.catalog_html()[:5000]})
        rec = guardrails.run_record("r", "", "", fx.SOURCES, pages, info, checks, False)
        self.assertEqual(rec["status"], "fail")
        self.assertFalse(rec["published"])

    def test_summary_table_lists_failures(self):
        checks, pages, _ = run(bodies={M6A.key: fx.catalog_html()[:5000]})
        text = guardrails.summary_table(fx.SOURCES, pages, checks, None)
        self.assertIn("FAILED CHECKS", text)
        self.assertIn("catalog/m6a", text)


if __name__ == "__main__":
    unittest.main()
