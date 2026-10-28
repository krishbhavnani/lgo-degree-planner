"""Source registry, thresholds and fetch settings for the data pipeline."""

import os

REPO_URL = "https://github.com/krishbhavnani/lgo-degree-planner"
USER_AGENT = "lgo-degree-planner/1.0 (+%s; unofficial MIT LGO course planner)" % REPO_URL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Local checkout (git worktree) of the public `data` branch that holds raw snapshots.
ARCHIVE_DIR = os.path.join(ROOT, ".data")

CATALOG_URL = "https://student.mit.edu/catalog/{}.html"
AAGS_URL = "https://eecsis.mit.edu/degree_requirements.pcgi?program=AAGS"
CATALOG_INDEX_URL = "https://student.mit.edu/catalog/index.cgi"
EECS_UPDATES_URL = "https://www.eecs.mit.edu/academics/subject-updates/"
DESIGN_URL = ("https://lgo-handbook.mit.edu/students/academic-guide/"
              "overview-of-academic-requirements/appendix-2-preapproved-design-classes/")
AL_URL = "https://mitsloan.mit.edu/action-learning"
AL_LABS_URL = "https://mitsloan.mit.edu/action-learning/explore-our-labs"

# Departments to scrape. `code` is the subject-number prefix and the OSE department id;
# `aags` flags the EECS AAGS approved-subject list (only meaningful for Course 6).
CATALOG_DEPARTMENTS = [
    {"code": "6", "name": "Course 6 — EECS", "pages": ["m6a", "m6b", "m6c", "m6d"], "aags": True},
    {"code": "15", "name": "Course 15 — Management", "pages": ["m15a", "m15b", "m15c"],
     "aags": False},
    {"code": "2", "name": "Course 2 — MechE", "pages": ["m2a", "m2b", "m2c"], "aags": False},
]
# Common Ground for Computing Education pages: (page, section heading to keep or None = all).
CG_SOURCES = [("mCGa", None), ("m6e", "Common Ground for Computing Education")]


def catalog_pages():
    pages = [p for d in CATALOG_DEPARTMENTS for p in d["pages"]] + [p for p, _ in CG_SOURCES]
    return list(dict.fromkeys(pages))


# --- Polite fetching -------------------------------------------------------
MIN_DELAY_PER_HOST = 1.5      # seconds between requests to the same host
TIMEOUT = 60                  # seconds per request
RETRIES = 3                   # retries after the first attempt (timeouts, 5xx, network errors)
BACKOFF = 2.0                 # seconds; doubles each retry (2, 4, 8)

# --- Guardrails ------------------------------------------------------------
MIN_PAGE_BYTES = 20 * 1024    # anything smaller is a broken/empty page
MAX_DROP = 0.30               # fail if a count falls more than 30% below the last passing run
# Run-wide floors for required fields on parsed graduate courses
# (calibrated 2026-10-27: title 99.7%, units 84.5%, description 100%).
MIN_TITLE_SHARE = 0.95
MIN_UNITS_SHARE = 0.70
MIN_DESC_SHARE = 0.90
# Per page: fail if a field share drops more than this (absolute) below the last passing run.
# Some pages are legitimately low on units (m2c 51%, m15c 62%: thesis / "arranged").
MAX_FIELD_SHARE_DROP = 0.25

# Signs that a public URL returned a login / single-sign-on page instead of content.
LOGIN_HOSTS = ("idp.mit.edu", "idp.touchstonenetwork.net", "login.mit.edu", "okta.mit.edu")
LOGIN_MARKERS = ('type="password"', "type='password'", "samlrequest", "touchstone@mit",
                 "mit touchstone", "shibboleth")


class Source:
    """One fetchable page. `kind` groups snapshots on the data branch (snapshots/<kind>/<page>/)
    and names the extract it feeds (extracts/<kind>.json).

    secondary  if True, a failure keeps that source's last good extract (run still publishes,
               but exits non-zero); catalog and AAGS failures block publishing.
    normalize  "catalog": ignore the daily Produced stamp / expires tag when detecting changes;
               "html": also ignore scripts, comments and whitespace (WordPress timing comments);
               "none": compare raw bytes (PDFs).
    """

    def __init__(self, kind, page, url, cache_name=None, ext=".html", min_bytes=None,
                 normalize="catalog", secondary=False):
        self.kind = kind
        self.page = page
        self.url = url
        self.ext = ext
        self.cache_name = cache_name or "%s__%s%s" % (kind, page, ext)
        self.min_bytes = MIN_PAGE_BYTES if min_bytes is None else min_bytes
        self.normalize = normalize
        self.secondary = secondary

    @property
    def key(self):
        return "%s/%s" % (self.kind, self.page)

    def __repr__(self):
        return "Source(%s)" % self.key

    def __eq__(self, other):
        return isinstance(other, Source) and other.key == self.key

    def __hash__(self):
        return hash(self.key)


def catalog_source(page):
    return Source("catalog", page, CATALOG_URL.format(page), "%s.html" % page)


AAGS_SOURCE = Source("aags", "aags", AAGS_URL, "aags.html")

# Secondary sources (B30 ticket 2b). Pages found by following links are added at run time
# by each source module's discover() (EECS semester pages + fragments, the AL booklet PDF).
CATALOG_INDEX_SOURCE = Source("catalog-index", "index", CATALOG_INDEX_URL, min_bytes=5 * 1024,
                              secondary=True)
EECS_UPDATES_SOURCE = Source("eecs-updates", "index", EECS_UPDATES_URL, normalize="html",
                             secondary=True)
DESIGN_SOURCE = Source("design", "appendix-2", DESIGN_URL, normalize="html", secondary=True)
AL_PAGE_SOURCE = Source("action-learning", "index", AL_URL, normalize="html", secondary=True)
AL_LABS_SOURCE = Source("action-learning", "labs", AL_LABS_URL, normalize="html",
                        secondary=True)


def build_sources(catalog_pages, secondary=True):
    """Static registry for a run: catalog pages (in order, de-duplicated), the AAGS page, and
    (unless secondary=False) the secondary sources."""
    seen, out = set(), []
    for p in catalog_pages:
        if p not in seen:
            seen.add(p)
            out.append(catalog_source(p))
    out.append(AAGS_SOURCE)
    if secondary:
        out += [CATALOG_INDEX_SOURCE, EECS_UPDATES_SOURCE, DESIGN_SOURCE, AL_PAGE_SOURCE,
                AL_LABS_SOURCE]
    return out
