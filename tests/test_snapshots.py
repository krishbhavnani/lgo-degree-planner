import gzip
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from pipeline import config, snapshots
from tests import fixtures as fx


class NormalizeTest(unittest.TestCase):
    def test_daily_stamp_and_expiry_ignored(self):
        a = fx.catalog_html(produced="26-OCT-2026 05:10 PM", expires="27 OCT 2026")
        b = fx.catalog_html(produced="27-OCT-2026 05:10 PM", expires="28 OCT 2026")
        self.assertNotEqual(a, b)
        self.assertEqual(snapshots.content_hash(a), snapshots.content_hash(b))

    def test_real_change_detected(self):
        a = fx.catalog_html(n_subjects=40)
        b = fx.catalog_html(n_subjects=41)
        self.assertNotEqual(snapshots.content_hash(a), snapshots.content_hash(b))

    def test_produced_stamp_parsed(self):
        raw, dt = snapshots.produced_stamp(fx.catalog_html().decode())
        self.assertEqual(raw, "27-OCT-2026 05:10 PM")
        self.assertEqual(dt, datetime(2026, 10, 27, 17, 10))

    def test_produced_stamp_unparseable(self):
        raw, dt = snapshots.produced_stamp("<p>Produced: sometime soon</p>")
        self.assertEqual(raw, "sometime soon")
        self.assertIsNone(dt)
        self.assertEqual(snapshots.produced_stamp("<p>nothing</p>"), (None, None))


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lgo-dp-test-")
        self.archive = snapshots.Archive(self.dir)
        self.src = config.catalog_source("m6a")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def at(self, day):
        return datetime(2026, 10, day, 22, 0, tzinfo=timezone.utc)

    def test_change_only_storage(self):
        e1 = self.archive.record("r1", self.src, fx.result(fx.catalog_html(), when=self.at(26)),
                                 "pass")
        self.assertEqual(e1["stored"], "snapshots/catalog/m6a/2026-10-26T220000Z.html.gz")
        # Next day: only the Produced stamp moved -> not stored again.
        body2 = fx.catalog_html(produced="28-OCT-2026 05:10 PM", expires="29 OCT 2026")
        e2 = self.archive.record("r2", self.src, fx.result(body2, when=self.at(27)), "pass")
        self.assertNotIn("stored", e2)
        self.assertEqual(e2["unchanged_since"], e1["stored"])
        # Real change -> stored.
        e3 = self.archive.record("r3", self.src,
                                 fx.result(fx.catalog_html(n_subjects=41), when=self.at(28)),
                                 "pass")
        self.assertIn("stored", e3)
        files = os.listdir(os.path.join(self.dir, "snapshots", "catalog", "m6a"))
        self.assertEqual(len(files), 2)
        self.assertEqual(len(self.archive.manifest()), 3)

    def test_raw_bytes_preserved_and_gzip_deterministic(self):
        body = fx.catalog_html()
        e = self.archive.record("r1", self.src, fx.result(body), "pass")
        path = os.path.join(self.dir, e["stored"])
        with open(path, "rb") as f:
            gz = f.read()
        self.assertEqual(gzip.decompress(gz), body)
        self.assertEqual(gz, gzip.compress(body, compresslevel=9, mtime=0))

    def test_state_survives_reload(self):
        self.archive.record("r1", self.src, fx.result(fx.catalog_html()), "pass")
        fresh = snapshots.Archive(self.dir)
        e = fresh.record("r2", self.src, fx.result(fx.catalog_html(), when=self.at(28)), "pass")
        self.assertIn("unchanged_since", e)

    def test_failed_run_snapshot_kept_and_marked(self):
        e = self.archive.record("r1", self.src, fx.result(b"<html>truncated"), "fail")
        self.assertEqual(e["run_status"], "fail")
        self.assertIn("stored", e)

    def test_login_page_never_stored(self):
        e = self.archive.record("r1", self.src, fx.result(fx.login_html()), "fail", login=True)
        self.assertTrue(e["login_page"])
        self.assertNotIn("stored", e)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "snapshots", "catalog")))

    def test_no_body_not_stored(self):
        e = self.archive.record("r1", self.src, fx.result(b"", status=None), "fail")
        self.assertNotIn("stored", e)
        self.assertNotIn("hash", e)

    def test_readme_written(self):
        self.archive.ensure_layout()
        self.assertTrue(os.path.exists(os.path.join(self.dir, "README.md")))

    def test_baseline_is_last_passing_run(self):
        self.archive.record_run({"run_id": "s", "status": "seed"})
        self.assertEqual(self.archive.baseline_run()["run_id"], "s")
        self.archive.record_run({"run_id": "a", "status": "pass"})
        self.archive.record_run({"run_id": "b", "status": "fail"})
        self.assertEqual(self.archive.baseline_run()["run_id"], "a")


if __name__ == "__main__":
    unittest.main()
