"""MIT Sloan Action Learning -> lab designations.

Sources
  mitsloan.mit.edu/action-learning               links the course booklet PDF (discovered)
  booklet PDF                                     which course numbers are labs (authoritative)
  mitsloan.mit.edu/action-learning/explore-our-labs   lab names only (early-warning check)

The catalog lists the lab courses but doesn't mark them, and three labs (15.S04, 15.S17,
15.S67) are only "Special Seminar in Management" there, so the booklet is the authority. To
depend on it as little as possible:
  1. The booklet only answers "is this a lab, and which" (number, lab label, name). Title,
     terms and units come from the catalog like any course.
  2. Booklets are kept per academic year in the extract; a late or missing booklet never
     breaks a run (the last good one stays).
  3. If this academic year's booklet isn't out yet, labs from the latest earlier booklet carry
     over: regular numbers while the catalog title is unchanged; special-subject numbers
     (15.Sxx, reused for other topics) are marked "unconfirmed".
  4. Lab names on the Sloan web page that match nothing known are reported (info only).

Booklet layout: two labs per page. Each lab has a large display label ("A-LAB", "ASEAN LAB",
"LWI"), a small course number beside it, the title in small capitals underneath, and a
"TERM ..." line. Text positions (not reading order) separate the labs. Needs pypdf.
"""

import io
import re
from urllib.parse import unquote

from .. import config
from .common import strip_tags

_PDF_LINK_RE = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.I | re.S)
_NUM_RE = re.compile(r"\b15\.(?:S\d{2,3}|\d{3})\b")
_CODE_RE = re.compile(r"\b([A-Z]{1,12}-LAB)\b")
_TERM_RE = re.compile(r"^(?:FALL|SPRING|IAP|SUMMER)(?:\s*[+&]\s*(?:FALL|SPRING|IAP|SUMMER))*")
_AY_RE = re.compile(r"\b(20\d\d)\s*[–-]\s*(20\d\d)\b")
LABEL_MIN_SIZE = 13.0      # display labels are 14-28pt; body text is 9-11pt
_SMALL = {"and", "or", "of", "in", "the", "to", "for", "on", "a", "an", "at", "by", "with",
          "from"}
_ACRONYMS = {"AI", "MIT", "US", "U.S.", "CRE", "PM", "IB", "PE", "LGO", "MBA", "IAP", "MVP",
             "LLM", "ASEAN", "SSIM", "MENA", "VC"}


def nice_title(upper):
    """'DEFENSE AND DUAL-USE VENTURES LAB' -> 'Defense and Dual-Use Ventures Lab' (keeps AI...)."""
    out = []
    for i, w in enumerate((upper or "").split()):
        core = re.sub(r"[^A-Z.]", "", w.upper())
        if core in _ACRONYMS or re.fullmatch(r"[A-Z]+-LAB", w):
            out.append(w.upper())
        elif i > 0 and w.lower() in _SMALL and not out[-1].endswith(":"):
            out.append(w.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def booklet_link(page_html, base="https://mitsloan.mit.edu"):
    """URL of the newest course-booklet PDF linked from the Action Learning page, or None."""
    best = None
    for href, text in _PDF_LINK_RE.findall(page_html):
        label = unquote(href) + " " + strip_tags(text)   # "Fall%202026" -> "Fall 2026"
        if not re.search(r"booklet|lab", label, re.I):
            continue
        years = [int(y) for y in re.findall(r"(?<!\d)20\d\d(?!\d)", label)]
        score = max(years) if years else 0
        url = "https:" + href if href.startswith("//") else (
            base + href if href.startswith("/") else href)
        if best is None or score > best[0]:
            best = (score, url)
    return best[1] if best else None


def discover(sources, results):
    page = results.get(config.AL_PAGE_SOURCE.key)
    if not page or not page.ok:
        return []
    url = booklet_link(page.text())
    if not url:
        return []
    return [config.Source("action-learning", "booklet", url, ext=".pdf", normalize="none",
                          min_bytes=50 * 1024, secondary=True)]


# ---------------------------------------------------------------------------
# Booklet parsing
# ---------------------------------------------------------------------------
def _fragments(page):
    """[(x, y, text, size)] for every text piece on a pypdf page."""
    out = []

    def visit(text, cm, tm, font, size):
        if not text.strip():
            return
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        scale = max(abs(tm[0]), abs(tm[3]), 1) * max(abs(cm[0]), abs(cm[3]), 1)
        out.append((x, y, text.strip(), round(size * scale, 1)))

    page.extract_text(visitor_text=visit)
    return out


def parse_page(frags, layout_text=""):
    """Labs on one booklet page: [{numbers, label, code, name, term}]."""
    labels = []
    for x, y, t, s in sorted(frags, key=lambda f: -f[1]):
        if s < LABEL_MIN_SIZE or not re.search(r"[A-Z]", t):
            continue
        # Multi-line labels ("INVESTMENT" / "MANAGEMENT LAB") share x and size.
        for lab in labels:
            if abs(lab["x"] - x) < 4 and lab["size"] == s and 0 < lab["y_low"] - y < 45:
                lab["label"] += " " + t
                lab["y_low"] = y
                break
        else:
            labels.append({"x": x, "y": y, "y_low": y, "size": s, "label": t})
    nums = [(x, y, m.group(0)) for x, y, t, s in frags if s < LABEL_MIN_SIZE and y > 1
            for m in [_NUM_RE.match(t)] if m]
    labs, used = [], set()
    for lab in labels:
        # Course number: on the same side of the page, level with the label's top line.
        cands = [(abs(ny - lab["y"]), n) for nx, ny, n in nums
                 if n not in used and abs(ny - lab["y"]) < 40 and (nx < 405) == (lab["x"] < 405)]
        number = min(cands)[1] if cands else None
        if number:
            used.add(number)
        below = [(y, t) for x, y, t, s in frags
                 if abs(x - lab["x"]) < 6 and s < LABEL_MIN_SIZE and
                 0 < lab["y_low"] - y < 70 and not re.search(r"[a-z]", t)]
        name = " ".join(t for y, t in sorted(below, reverse=True) if not _NUM_RE.search(t))
        term = None
        for x, y, t, s in frags:
            if t == "TERM" and abs(x - lab["x"]) < 8 and y < lab["y"]:
                vals = [(vx, vt) for vx, vy, vt, vs in frags if abs(vy - y) < 2 and vx > x]
                if vals:
                    m = _TERM_RE.match(min(vals)[1].replace(" ", ""))
                    term = m.group(0) if m else None
                break
        code = _CODE_RE.search(lab["label"])
        labs.append({"number": number, "label": lab["label"],
                     "code": code.group(1) if code else None,
                     "name": nice_title(name) if name else None, "term": term})
    # A number drawn without a usable position (seen on one page): if exactly one label and
    # one number on the page are unmatched, pair them (numbers come from the text layout).
    missing = [lab for lab in labs if not lab["number"]]
    leftover = [n for n in dict.fromkeys(_NUM_RE.findall(layout_text.split("\n", 3)[0]
                                                         if layout_text else ""))
                if n not in used]
    if len(missing) == 1 and len(leftover) == 1:
        missing[0]["number"] = leftover[0]
    return [lab for lab in labs if lab["number"]]


def parse_booklet(pdf_bytes):
    """{"academic_year": "2026-2027" or None, "labs": [...]} from the booklet PDF bytes."""
    import pypdf  # the repo's one third-party dependency (requirements.txt)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    ay = None
    first = reader.pages[0].extract_text() or ""
    m = _AY_RE.search(first)
    if m and int(m.group(2)) == int(m.group(1)) + 1:
        ay = "%s-%s" % (m.group(1), m.group(2))
    labs = []
    for i, page in enumerate(reader.pages):
        layout = page.extract_text(extraction_mode="layout") or ""
        lines = [ln.strip() for ln in layout.splitlines() if ln.strip()]
        for lab in parse_page(_fragments(page), "\n".join(lines[:3])):
            lab["page"] = i + 1
            labs.append(lab)
    return {"academic_year": ay, "labs": labs}


def lab_names(labs_page_html):
    """Lab names listed on the Sloan 'Explore our labs' page."""
    html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", labs_page_html, flags=re.S)
    names = []
    for t in re.findall(r">([^<>]{3,80})<", html):
        t = re.sub(r"\s+", " ", t).strip()
        if re.search(r"\bLab\b", t) and len(t) < 80 and t not in names and \
                not re.search(r"\b(?:explore|our labs|action learning)\b", t, re.I):
            names.append(t)
    return names


# ---------------------------------------------------------------------------
# Extract (merged with the previous extract so booklets accumulate per academic year)
# ---------------------------------------------------------------------------
def extract(sources, results, previous=None):
    problems = []
    booklets = dict((previous or {}).get("booklets", {}))
    src = next((s for s in sources if s.key == "action-learning/booklet"), None)
    res = results.get(src.key) if src else None
    if src is None:
        problems.append(("fail", "no booklet PDF link found on the Action Learning page"))
    elif not res or not res.ok:
        problems.append(("fail", "booklet PDF not fetched"))
    else:
        try:
            b = parse_booklet(res.body)
        except ImportError:
            b = None
            problems.append(("fail", "pypdf is not installed (pip install -r requirements.txt)"))
        except Exception as e:  # unreadable PDF -> keep the last good booklet
            b = None
            problems.append(("fail", "booklet unreadable: %s: %s" % (type(e).__name__, e)))
        if b is not None:
            if not b["academic_year"]:
                problems.append(("fail", "booklet cover has no academic year"))
            elif len(b["labs"]) < 5:
                problems.append(("fail", "booklet: only %d labs found" % len(b["labs"])))
            else:
                for lab in b["labs"]:
                    lab["_page"] = src.key
                booklets[b["academic_year"]] = {"url": src.url, "labs": b["labs"]}
    keep = sorted(booklets)[-3:]     # current, next and one earlier academic year at most
    booklets = {ay: booklets[ay] for ay in keep}
    labs_res = results.get(config.AL_LABS_SOURCE.key)
    names = lab_names(labs_res.text()) if labs_res and labs_res.ok else \
        (previous or {}).get("labs_page_names", [])
    records = [dict(lab, academic_year=ay) for ay, b in booklets.items() for lab in b["labs"]]
    return {"booklets": booklets, "labs_page_names": names,
            "designations": (previous or {}).get("designations", {}),
            "records": records, "problems": problems}


def _norm(t):
    t = re.sub(r"^\[J\]\s*", "", t or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _words(text):
    stop = {"lab", "labs", "and", "the", "a", "of", "in", "for", "on"}
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("&", "and"))
            if w not in stop}


def resolve(al_extract, catalog_records, academic_year):
    """Designations for this academic year: ({number: info}, notes).

    info = {code, name, term, booklet_year, status: "confirmed"|"carried"|"unconfirmed"}.
    Also stores the result in al_extract["designations"] (with each course's catalog title) so
    a later run without a new booklet can tell whether a regular-numbered lab is unchanged.
    """
    by_num = {r["number"]: r for r in catalog_records}
    by_title = {}
    for r in catalog_records:
        by_title.setdefault(_norm(r.get("title")), []).append(r["number"])
    booklets = al_extract.get("booklets", {})
    notes, out = [], {}
    if academic_year in booklets:
        for lab in booklets[academic_year]["labs"]:
            info = {"code": lab["code"] or lab["label"], "name": lab["name"],
                    "term": lab["term"], "booklet_year": academic_year, "status": "confirmed"}
            number = lab["number"]
            if number not in by_num:
                # e.g. the booklet lists LWI as 15.S24 (only inside a catalog range row) while
                # the catalog has 15.335 "Leading with Impact: A Social Impact Lab".
                hits = [n for n in by_title.get(_norm(lab["name"]), []) if n not in out]
                if hits:
                    notes.append("booklet lists %s %s as %s; matched catalog %s by title" %
                                 (info["code"], lab["name"], number, ", ".join(hits)))
                    for n in hits:
                        out[n] = dict(info, booklet_number=number)
                    continue
            out[number] = info
    else:
        earlier = [ay for ay in booklets if ay < (academic_year or "")]
        prev = al_extract.get("designations", {})
        if earlier:
            notes.append("no %s booklet yet; carrying labs over from %s" %
                         (academic_year, max(earlier)))
        for n, d in prev.items():
            cur = by_num.get(n)
            if not cur:
                continue
            if re.match(r"15\.S", n):
                out[n] = dict(d, status="unconfirmed")
            elif cur.get("title") == d.get("catalog_title"):
                out[n] = dict(d, status="carried")
    for n, d in out.items():
        if n in by_num:
            d["catalog_title"] = by_num[n].get("title")
    al_extract["designations"] = {n: d for n, d in out.items() if n in by_num}

    known = [_words(" ".join(filter(None, [d.get("name"), d.get("code"),
                                           (by_num.get(n) or {}).get("title")])))
             for n, d in out.items()]
    for name in al_extract.get("labs_page_names", []):
        w = _words(name.split(":")[0])
        if w and not any(w <= k for k in known):
            notes.append("Sloan labs page lists %r, not matched to a known lab" % name)
    return out, notes
