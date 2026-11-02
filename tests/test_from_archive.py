"""End-to-end --from-archive: write the site files from the data branch without fetching.

Skipped without the archive (.data/ or $LGO_DP_ARCHIVE), like the scenario fixtures.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import scrape
from pipeline import config

ARCHIVE = os.environ.get("LGO_DP_ARCHIVE", config.ARCHIVE_DIR)
HAVE = os.path.exists(os.path.join(ARCHIVE, "runs.jsonl"))


def read_js(path, var):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return json.loads(text[len("window.%s = " % var):].rstrip().rstrip(";"))


class NoFetch:
    def get(self, url):
        raise AssertionError("--from-archive must not fetch %s" % url)


@unittest.skipUnless(HAVE, "no archive (run from a checkout with .data/)")
class FromArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lgo-dp-out-")
        self.out = os.path.join(self.tmp, "site")   # doesn't exist yet, like _site on a runner
        self.argv = sys.argv

    def tearDown(self):
        sys.argv = self.argv
        shutil.rmtree(self.tmp)

    def test_rebuilds_site_files_without_fetching(self):
        sys.argv = ["scrape.py", "--from-archive", "--archive-dir", ARCHIVE, "--out", self.out]
        real_fetcher = scrape.Fetcher
        scrape.Fetcher = NoFetch          # any live fetch would raise
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = scrape.main()
        finally:
            scrape.Fetcher = real_fetcher
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(self.out)), ["changes.js", "db.js", "programs.js"])
        db = read_js(os.path.join(self.out, "db.js"), "COURSE_DB")
        with open(os.path.join(ARCHIVE, "db", "courses.json"), encoding="utf-8") as f:
            stored = json.load(f)
        with open(os.path.join(ARCHIVE, "extracts", "catalog.json"), encoding="utf-8") as f:
            years = json.load(f)["years"]
        self.assertGreater(db["meta"]["course_count"], 500)
        self.assertEqual(db["meta"]["course_count"], len(stored["courses"]))
        self.assertEqual(db["meta"]["updated"], stored["updated"])
        self.assertEqual(db["meta"]["current_term"], years["term"])
        programs = read_js(os.path.join(self.out, "programs.js"), "PROGRAMS")
        self.assertIn("lgo", programs)
        self.assertTrue(all(p.get("extends") == "lgo" for k, p in programs.items() if k != "lgo"))

    def test_site_writers_create_the_output_folder(self):
        nested = os.path.join(self.out, "a", "b")
        scrape.write_programs_js(nested)
        with open(os.path.join(ARCHIVE, "extracts", "catalog.json"), encoding="utf-8") as f:
            scrape.write_db_js(ARCHIVE, json.load(f)["years"], os.path.join(self.out, "c"))
        self.assertTrue(os.path.exists(os.path.join(nested, "programs.js")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "c", "db.js")))

    def test_archive_unchanged(self):
        before = {f: os.path.getmtime(os.path.join(ARCHIVE, f))
                  for f in ("manifest.jsonl", "runs.jsonl")}
        sys.argv = ["scrape.py", "--from-archive", "--archive-dir", ARCHIVE, "--out", self.out]
        with contextlib.redirect_stdout(io.StringIO()):
            scrape.main()
        after = {f: os.path.getmtime(os.path.join(ARCHIVE, f)) for f in before}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
