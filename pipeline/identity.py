"""Course identity.

Regular subjects: the number is the identity (renumberings link through aliases).
Special subjects (X.Sxxx): MIT reuses the number for a different topic each term, so the
identity is number + topic title, e.g. "15.S04~generative-ai-lab". Evaluations, design and
Action Learning designations attach to a special subject only when the title matches.
Range rows ("15.840-15.843"): the range label is the identity.

Renumberings
  - explicit notes on EECS subject updates ("NEW 6.7980 ... (was 6.S890)") are accepted
    automatically;
  - lookalikes (a course disappears in the same run a new number appears with a near-identical
    title and description) are only flagged; Krish confirms them in aliases.json.
"""

import difflib
import json
import os
import re

SPECIAL_RE = re.compile(r"^[0-9A-Z]+\.S\d")
TITLE_MATCH_MIN = 0.90       # lookalike renumbering: title similarity
DESC_MATCH_MIN = 0.80        # ... and description similarity


def is_special(number):
    return bool(SPECIAL_RE.match(number or ""))


def is_range(number):
    return "-" in (number or "")


def clean_title(title):
    """Drop the catalog's joint-subject marker: '[J] Product Design' -> 'Product Design'."""
    return re.sub(r"^\[J\]\s*", "", title or "").strip()


def norm_title(title):
    t = clean_title(title).lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def titles_match(a, b):
    return bool(a) and bool(b) and norm_title(a) == norm_title(b)


def slug(title):
    return re.sub(r"\s+", "-", norm_title(title))[:60] or "untitled"


def course_id(number, topic_title=None):
    if is_special(number) and not is_range(number):
        return "%s~%s" % (number, slug(topic_title))
    return number


def load_aliases(path):
    """aliases.json: {"aliases": [{"old": "15.335", "new": "15.703", "note": "..."}]}."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [a for a in data.get("aliases", []) if a.get("old") and a.get("new")]


def _ratio(a, b):
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def renumber_candidates(removed, added):
    """Pairs (old course, new course) that look like the same subject under a new number.

    removed/added: course records that left / appeared in this run (regular subjects only).
    """
    out = []
    for old in removed:
        if is_special(old["number"]) or is_range(old["number"]):
            continue
        for new in added:
            if is_special(new["number"]) or is_range(new["number"]):
                continue
            t = _ratio(old.get("title"), new.get("title"))
            if t < TITLE_MATCH_MIN:
                continue
            d = difflib.SequenceMatcher(None, old.get("description") or "",
                                        new.get("description") or "").ratio()
            if d >= DESC_MATCH_MIN:
                out.append({"old": old["id"], "new": new["id"], "title_similarity": round(t, 2),
                            "description_similarity": round(d, 2)})
    return out
