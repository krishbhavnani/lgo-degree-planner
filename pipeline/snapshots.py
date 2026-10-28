"""Change-only, gzipped raw-page archive (the public `data` branch).

Layout under the archive root (a git worktree of the `data` branch):

    README.md
    snapshots/<kind>/<page>/<YYYY-MM-DDTHHMMSSZ>.html.gz   raw page bytes, exactly as served
    manifest.jsonl    one line per page fetch (stored, or unchanged since an earlier file)
    runs.jsonl        one line per run (pass/fail, every check, page counts)

A page is stored only when its normalized content changed. Normalizing removes the parts
MIT regenerates daily without any content change: the "Produced: DD-MON-YYYY hh:mm PM"
stamp and the <meta http-equiv="expires"> tag. The stored file is the raw page, not the
normalized one. This module only writes files; it never commits or pushes.
"""

import gzip
import hashlib
import json
import os
import re
from datetime import datetime, timezone

_PRODUCED_RE = re.compile(rb"Produced:\s*[^<\r\n]*", re.I)
_EXPIRES_RE = re.compile(rb"<meta\s+http-equiv\s*=\s*[\"']?expires[\"']?[^>]*>", re.I)
_PRODUCED_TEXT_RE = re.compile(r"Produced:\s*([^<\r\n]+)", re.I)

README = """# `data` branch — raw source snapshots

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
"""


def normalize(body):
    """Bytes with the volatile daily stamp/expiry removed (used only for change detection)."""
    body = _PRODUCED_RE.sub(b"Produced:", body)
    return _EXPIRES_RE.sub(b"", body)


def content_hash(body):
    return hashlib.sha256(normalize(body)).hexdigest()


def produced_stamp(text):
    """Return (raw stamp string or None, parsed datetime or None) for a catalog page."""
    m = _PRODUCED_TEXT_RE.search(text)
    if not m:
        return None, None
    raw = m.group(1).strip()
    try:
        return raw, datetime.strptime(raw.title(), "%d-%b-%Y %I:%M %p")
    except ValueError:
        return raw, None


def stamp(dt):
    """Filename-safe UTC timestamp, e.g. 2026-10-27T221500Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Archive:
    def __init__(self, root):
        self.root = root
        self.manifest_path = os.path.join(root, "manifest.jsonl")
        self.runs_path = os.path.join(root, "runs.jsonl")
        self._latest = None     # source key -> {"hash", "path"}

    # -- reading ----------------------------------------------------------
    def _read_jsonl(self, path):
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def manifest(self):
        return self._read_jsonl(self.manifest_path)

    def runs(self):
        return self._read_jsonl(self.runs_path)

    def latest(self):
        """Most recent saved content per source key: {"kind/page": {"hash", "path"}}."""
        if self._latest is None:
            self._latest = {}
            for e in self.manifest():
                path = e.get("stored") or e.get("unchanged_since")
                if path and e.get("hash"):
                    self._latest[e["source"]] = {"hash": e["hash"], "path": path}
        return self._latest

    def baseline_run(self):
        """The last passing run (falls back to the seed record before the first live pass)."""
        runs = self.runs()
        for status in ("pass", "seed"):
            for r in reversed(runs):
                if r.get("status") == status:
                    return r
        return None

    # -- writing ----------------------------------------------------------
    def ensure_layout(self):
        os.makedirs(os.path.join(self.root, "snapshots"), exist_ok=True)
        readme = os.path.join(self.root, "README.md")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write(README)

    def record(self, run_id, source, result, run_status, produced=None, login=False,
               seed=False):
        """Archive one fetch. Saves the raw page only if its content changed.

        Login pages and empty bodies are never saved (recorded in the manifest only).
        Returns the manifest entry.
        """
        self.ensure_layout()
        body = result.body or b""
        entry = {
            "run_id": run_id,
            "source": source.key,
            "url": source.url,
            "final_url": result.final_url if result.final_url != source.url else None,
            "fetched_at": iso(result.fetched_at),
            "http_status": result.status,
            "error": result.error,
            "via": result.via,
            "bytes": len(body),
            "produced": produced,
            "hash": None,
            "stored": None,
            "unchanged_since": None,
            "run_status": run_status,
        }
        if login:
            entry["login_page"] = True
        if seed:
            entry["seed"] = True
        if body and not login:
            h = content_hash(body)
            entry["hash"] = h
            prev = self.latest().get(source.key)
            if prev and prev["hash"] == h:
                entry["unchanged_since"] = prev["path"]
            else:
                rel = self._write_snapshot(source, result.fetched_at, body)
                entry["stored"] = rel
                self.latest()[source.key] = {"hash": h, "path": rel}
        entry = {k: v for k, v in entry.items() if v is not None}
        self._append(self.manifest_path, entry)
        return entry

    def record_run(self, run):
        self.ensure_layout()
        self._append(self.runs_path, run)

    def _write_snapshot(self, source, when, body):
        folder = os.path.join("snapshots", source.kind, source.page)
        os.makedirs(os.path.join(self.root, folder), exist_ok=True)
        name = stamp(when)
        rel = os.path.join(folder, name + ".html.gz")
        n = 1
        while os.path.exists(os.path.join(self.root, rel)):
            n += 1
            rel = os.path.join(folder, "%s-%d.html.gz" % (name, n))
        # mtime=0 keeps the gzip bytes deterministic for identical input.
        with open(os.path.join(self.root, rel), "wb") as f:
            f.write(gzip.compress(body, compresslevel=9, mtime=0))
        return rel.replace(os.sep, "/")

    def _append(self, path, obj):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, sort_keys=False) + "\n")
