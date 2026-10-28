# `data` branch — raw source snapshots

This branch is the raw-data archive for
[lgo-degree-planner](https://github.com/krishbhavnani/lgo-degree-planner). It is never merged
into `main`; the app does not read it.

Every scrape fetches the public source pages (MIT Subject Listing catalog pages and the EECS
AAGS approved-subject list) and saves a page **only when its content changed** since the last
saved copy, gzipped, exactly as served.

| Path | What it is |
|------|------------|
| `snapshots/<kind>/<page>/<UTC time>.html.gz` | raw page as fetched (`gunzip -c` to read) |
| `manifest.jsonl` | one line per page fetch: when, HTTP status, size, the page's `Produced:` stamp, content hash, and either the file saved or the earlier file it is unchanged from |
| `runs.jsonl` | one line per scrape run: pass/fail, every guardrail check, per-page counts |

Change detection ignores the daily `Produced:` stamp and the `<meta http-equiv="expires">`
tag, which change every day without any content change.

Snapshots from runs that failed a guardrail are kept too (marked `fail`) so a bad fetch can be
inspected. Entries marked `seed` were imported from earlier local caches when the archive
started (2026-10-27).

Login-gated sources (MIT subject evaluations) are never stored here. If a public source ever
returns a login page, the run fails and that page is not saved.

All course content belongs to MIT and its departments.
