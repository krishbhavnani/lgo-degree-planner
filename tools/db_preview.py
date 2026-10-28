#!/usr/bin/env python3
"""Preview what the next run would do to the course database, using cached pages only.

    python3 tools/db_preview.py            # summary of changes vs the stored database
    python3 tools/db_preview.py --show ID  # one course as it would be stored

Nothing is fetched or written (the stored database in .data/ is read, not changed).
"""

import contextlib
import io
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrape  # noqa: E402
from pipeline import config, snapshots  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        sources, results = scrape.collect(config.build_sources(config.catalog_pages()), False)
        payload, ex = scrape.build(sources, results, config.ARCHIVE_DIR)
    run_id = snapshots.stamp(datetime.now(timezone.utc))
    db, changes = scrape.update_db(config.ARCHIVE_DIR, ex["_context"], run_id, save=False)
    if "--show" in sys.argv:
        cid = sys.argv[sys.argv.index("--show") + 1]
        print(json.dumps(db["courses"].get(cid), indent=1, ensure_ascii=False))
        return
    c = db["courses"]
    print("courses: %d (%s)" % (len(c), dict(Counter(x["kind"] for x in c.values()))))
    print("offerings by term/status:")
    tally = Counter((t, o["status"]) for x in c.values() for t, o in x["offerings"].items())
    for t in sorted({t for t, _ in tally}, key=lambda t: scrape.terms.key(t)):
        print("  %-12s %s" % (t, ", ".join("%s %d" % (s, n) for (tt, s), n in
                                           sorted(tally.items()) if tt == t)))
    print("changes this run: %s" % dict(Counter(x["kind"] for x in changes)))


if __name__ == "__main__":
    main()
