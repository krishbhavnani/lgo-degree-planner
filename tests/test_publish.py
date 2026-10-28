import json
import os
import shutil
import tempfile
import unittest

from pipeline import db as cdb
from pipeline import publish
from tests.test_db import YEARS, row, run


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lgo-dp-test-")
        self.db = cdb.empty()
        run(self.db, [row("15.100", "Strategy", terms=("Fall", "Spring"))])

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_db_payload_shape(self):
        p = publish.db_payload(self.db, YEARS)
        self.assertEqual(p["meta"]["current_term"], "Fall 2026")
        self.assertEqual(p["meta"]["terms"], ["Fall 2026", "Spring 2027", "Fall 2027",
                                              "Spring 2028"])
        (c,) = p["courses"]
        self.assertEqual(c["id"], "15.100")
        self.assertNotIn("history", c)
        off = c["offerings"]["Fall 2026"]
        self.assertEqual(off["status"], "listed")
        self.assertNotIn("history", off)
        self.assertNotIn("title", off)                      # same as the course title
        self.assertNotIn("instructor", c["offerings"]["Fall 2027"])  # empty values dropped

    def test_feed_and_recent_changes(self):
        r = row("15.100", "Strategy", terms=("Fall", "Spring"))
        r["instructor"] = "B. New"
        changes = run(self.db, [r], "2026-11-04")
        publish.append_feed(self.dir, changes)
        publish.append_feed(self.dir, [{"date": "2026-01-01", "kind": "changed"}])
        feed = publish.read_feed(self.dir)
        self.assertEqual(len(feed), len(changes) + 1)
        recent = publish.changes_payload(feed, "2026-11-04")
        self.assertEqual(recent["since"], "2026-05-08")
        self.assertEqual(len(recent["changes"]), len(changes))   # the January entry is old

    def test_write_js(self):
        path = os.path.join(self.dir, "db.js")
        publish.write_js(path, "COURSE_DB", publish.db_payload(self.db, YEARS))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("window.COURSE_DB = {"))
        json.loads(text[len("window.COURSE_DB = "):].rstrip().rstrip(";"))


if __name__ == "__main__":
    unittest.main()
