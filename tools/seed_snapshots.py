#!/usr/bin/env python3
"""One-time import of earlier local page caches into the snapshot archive.

Only pages in the source registry are imported (catalog pages + the AAGS page), looked up by
their cache file name in:
    .scratch/<page>.html
    .scratch/snapshots/<folder>/<page>.html
Nothing else is read - in particular never .scratch/legacy/ (raw evaluation reports live there
and must not reach the public data branch). Identical copies are imported once. Each entry is
dated by the file's modification time (when it was fetched) and marked `seed`.

A `seed` run record is also written so the first live run has counts to compare against.

Run once, before the first live --refresh:
    python3 tools/seed_snapshots.py [--archive-dir PATH] [--force]
"""

import glob
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrape  # noqa: E402
from pipeline import config, guardrails, snapshots  # noqa: E402
from pipeline.fetch import FetchResult  # noqa: E402

SCRATCH = os.path.join(ROOT, ".scratch")


def candidates(cache_name):
    paths = [os.path.join(SCRATCH, cache_name)]
    paths += sorted(glob.glob(os.path.join(SCRATCH, "snapshots", "*", cache_name)))
    out = []
    for p in paths:
        if os.sep + "legacy" + os.sep in p:
            continue  # belt and braces: never import from .scratch/legacy/
        if os.path.isfile(p):
            out.append(p)
    return out


def main():
    archive_dir = config.ARCHIVE_DIR
    if "--archive-dir" in sys.argv:
        archive_dir = sys.argv[sys.argv.index("--archive-dir") + 1]
    if not os.path.isdir(archive_dir):
        sys.exit("No archive directory at %s (create the data worktree first)." % archive_dir)
    archive = snapshots.Archive(archive_dir)
    if archive.manifest() and "--force" not in sys.argv:
        sys.exit("Archive already has entries; seeding is a one-time step (use --force).")

    catalog_pages = [p for d in scrape.DEPARTMENTS for p in d["pages"]] + \
                    [p for p, _ in scrape.CG_SOURCES]
    sources = config.build_sources(catalog_pages)

    # Gather distinct copies per source, oldest first.
    found = []      # (mtime, source, path, body)
    for s in sources:
        seen = set()
        for path in candidates(s.cache_name):
            with open(path, "rb") as f:
                body = f.read()
            h = snapshots.content_hash(body)
            if h in seen:
                continue
            seen.add(h)
            found.append((os.path.getmtime(path), s, path, body))
    if not found:
        sys.exit("No cached pages found to seed.")
    found.sort(key=lambda t: t[0])
    first = datetime.fromtimestamp(found[0][0], timezone.utc)
    run_id = "seed-" + snapshots.stamp(first)

    newest = {}
    for mtime, s, path, body in found:
        when = datetime.fromtimestamp(mtime, timezone.utc)
        res = FetchResult(s.url, 200, body, via="cache", fetched_at=when)
        m = guardrails.page_metrics(s, res)
        e = archive.record(run_id, s, res, "seed", produced=m.get("produced"),
                           login=m.get("login", False), seed=True)
        print("  %-14s %s  <- %s" % (s.key, e.get("stored") or "unchanged",
                                      os.path.relpath(path, ROOT)))
        newest[s.key] = res

    # Baseline record from the newest copy of each page.
    results = {s.key: newest[s.key] for s in sources if s.key in newest}
    missing = [s.key for s in sources if s.key not in newest]
    pages = {s.key: guardrails.page_metrics(s, results[s.key])
             for s in sources if s.key in results}
    scrape._PAGES.clear()
    for s in sources:
        if s.key in results:
            scrape._PAGES[s.cache_name] = results[s.key]
    courses_info, parse_error = None, None
    if not missing:
        payload, scraped, aags_count = scrape.build()
        courses_info = guardrails.course_metrics(scraped, aags_count)
    else:
        parse_error = "missing seed pages: %s" % ", ".join(missing)
    checks = guardrails.evaluate(sources, results, pages, courses_info, None, parse_error)
    archive.record_run(guardrails.run_record(
        run_id, snapshots.iso(first), snapshots.iso(datetime.fromtimestamp(found[-1][0],
                                                                           timezone.utc)),
        sources, pages, courses_info, checks, published=False, mode="seed", seed=True))
    print(guardrails.summary_table(sources, pages, checks, None))
    print("\nSeeded %d snapshot(s) for %d source(s) into %s (run %s)." %
          (len(found), len(newest), archive_dir, run_id))


if __name__ == "__main__":
    main()
