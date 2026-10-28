"""Per-source extracts: normalized JSON written to the archive (data branch) as extracts/<name>.json.

Written only by runs that pass the guardrails, so each file is the latest good extract and its
git history on the data branch shows every change. A secondary source that failed this run keeps
its previous file (it is read back as the fallback). Every record carries where it came from:

    "_src": {"page": "catalog/m6a", "snapshot": "snapshots/catalog/m6a/...html.gz",
             "fetched_at": "2026-10-28T02:41:48Z"}

`snapshot` is the archived raw page this record was parsed from (the file saved in this run,
or the earlier identical one); `fetched_at` is when that snapshot was saved, so extracts only
change when a page's content does.
"""

import json
import os
import re

FORMAT = 1

# Fields filled later by the publish step, not by the source: kept out of extracts.
_PUBLISH_ONLY = {"prereqs", "aags", "rating", "rating_rationale", "eval_status", "eval_hours_in",
                 "eval_hours_out", "eval_responses", "eval_term", "eval_instructor",
                 "eval_instructor_match", "eval_url"}


_SNAP_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})(\d{2})Z")


def provenance(sources, entries):
    """{source key: {"page", "snapshot", "fetched_at"}} from this run's manifest entries.

    fetched_at is when the snapshot was saved (read from its file name), so an unchanged page
    keeps the same provenance and the extract only changes when the content does.
    """
    out = {}
    for s in sources:
        e = entries.get(s.key, {})
        snap = e.get("stored") or e.get("unchanged_since")
        m = _SNAP_TIME_RE.search(snap or "")
        when = "%sT%s:%s:%sZ" % m.groups() if m else e.get("fetched_at")
        out[s.key] = {"page": s.key, "url": s.url, "snapshot": snap, "fetched_at": when}
    return out


def _catalog_doc(ex, prov):
    records = []
    for r in ex["records"]:
        rec = {k: v for k, v in r.items() if k not in _PUBLISH_ONLY}
        src = prov.get("catalog/%s" % r["source_page"], {})
        rec["_src"] = {k: src.get(k) for k in ("page", "snapshot", "fetched_at")}
        records.append(rec)
    return {
        "years": ex["years"],
        "page_dates": ex["page_dates"],
        "ranges": ex["ranges"],
        "titles": ex["all_titles"],
        "records": records,
    }


def _aags_doc(ex, prov):
    src = prov.get("aags/aags", {})
    s = {k: src.get(k) for k in ("page", "snapshot", "fetched_at")}
    return {"records": [dict(r, _src=s) for r in ex["records"]]}


def _with_src(obj, prov):
    """Recursively replace each record's "_page" key with its "_src" provenance."""
    if isinstance(obj, list):
        return [_with_src(x, prov) for x in obj]
    if isinstance(obj, dict):
        out = {k: _with_src(v, prov) for k, v in obj.items() if k != "_page"}
        if "_page" in obj:
            src = prov.get(obj["_page"], {"page": obj["_page"]})
            out["_src"] = {k: src.get(k) for k in ("page", "snapshot", "fetched_at")}
        return out
    return obj


def _generic_doc(ex, prov):
    return _with_src({k: v for k, v in ex.items() if k not in ("problems", "_fallback")}, prov)


BUILDERS = {"catalog": _catalog_doc, "aags": _aags_doc, "catalog_index": _generic_doc,
            "eecs_updates": _generic_doc, "design": _generic_doc,
            "action_learning": _generic_doc}


def write_all(root, run_id, sources, entries, extracts):
    """Write extracts/<name>.json for every extract we know how to serialize."""
    prov = provenance(sources, entries)
    folder = os.path.join(root, "extracts")
    os.makedirs(folder, exist_ok=True)
    written = []
    for name, ex in extracts.items():
        build = BUILDERS.get(name)
        if not build or ex.get("_fallback"):
            continue  # unknown, or a secondary source that kept its last good extract
        doc = {"format": FORMAT, "source": name, "run_id": run_id}
        doc.update(build(ex, prov))
        path = os.path.join(folder, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        written.append("extracts/%s.json" % name)
    return written


def load(root, name):
    path = os.path.join(root, "extracts", name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
