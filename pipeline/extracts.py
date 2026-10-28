"""Per-source extracts: normalized JSON written to the archive (data branch) as extracts/<name>.json.

Written only by runs that pass the guardrails, so each file is the latest good extract and its
git history on the data branch shows every change. Every record carries where it came from:

    "_src": {"page": "catalog/m6a", "snapshot": "snapshots/catalog/m6a/...html.gz",
             "fetched_at": "2026-10-28T02:41:48Z"}

`snapshot` is the archived raw page this record was parsed from (the file saved in this run,
or the earlier identical one).
"""

import json
import os

FORMAT = 1

# Fields filled later by the publish step, not by the source: kept out of extracts.
_PUBLISH_ONLY = {"prereqs", "aags", "rating", "rating_rationale", "eval_status", "eval_hours_in",
                 "eval_hours_out", "eval_responses", "eval_term", "eval_instructor",
                 "eval_instructor_match", "eval_url"}


def provenance(sources, entries):
    """{source key: {"page", "snapshot", "fetched_at"}} from this run's manifest entries."""
    out = {}
    for s in sources:
        e = entries.get(s.key, {})
        out[s.key] = {"page": s.key, "url": s.url,
                      "snapshot": e.get("stored") or e.get("unchanged_since"),
                      "fetched_at": e.get("fetched_at")}
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


BUILDERS = {"catalog": _catalog_doc, "aags": _aags_doc}


def write_all(root, run_id, sources, entries, extracts):
    """Write extracts/<name>.json for every extract we know how to serialize."""
    prov = provenance(sources, entries)
    folder = os.path.join(root, "extracts")
    os.makedirs(folder, exist_ok=True)
    written = []
    for name, ex in extracts.items():
        build = BUILDERS.get(name)
        if not build:
            continue
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
