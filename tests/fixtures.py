"""Small synthetic catalog/AAGS pages for tests (no real MIT pages are committed)."""

from datetime import datetime, timezone

from pipeline import config
from pipeline.fetch import FetchResult


def catalog_html(n_subjects=40, produced="27-OCT-2026 05:10 PM", expires="28 OCT 2026",
                 body_note="", pad_to=25 * 1024):
    blocks = []
    for i in range(n_subjects):
        num = "6.%d" % (5000 + i)
        blocks.append(
            '<a name="%s"></a><p><h3>%s Example Subject %d<br></h3>'
            '<img alt="Graduate"><img alt="Fall">'
            "<br>Units: 3-0-9<br><img src=hr.gif><img src=hr.gif>"
            "A description of subject %d. <I>A. Teacher</I><!--end-->" % (num, num, i, i))
    page = ('<html><head><meta http-equiv="expires" content="%s" ><title>Catalog</title>'
            "</head><body>%s%s<p>Produced: %s</p></body></html>"
            % (expires, body_note, "\n".join(blocks), produced))
    if len(page) < pad_to:
        page = page.replace("</body>", "<!--%s--></body>" % ("x" * (pad_to - len(page))))
    return page.encode("utf-8")


def login_html():
    return (b"<html><head><title>MIT Touchstone</title></head><body>"
            b'<form action="https://idp.mit.edu/idp/profile/SAML2/Redirect/SSO">'
            b'<input type="password" name="j_password"></form></body></html>') + b" " * 30000


def result(body, url="https://student.mit.edu/catalog/m6a.html", status=200, final_url=None,
           when=None):
    return FetchResult(url, status, body, final_url=final_url,
                       fetched_at=when or datetime(2026, 10, 27, 22, 0, tzinfo=timezone.utc))


def courses(n, page="m6a", titled=1.0, with_units=1.0, with_desc=1.0):
    out = []
    for i in range(n):
        out.append({
            "number": "6.%d" % (5000 + i),
            "title": "Subject %d" % i if i < n * titled else "",
            "units_total": 12 if i < n * with_units else None,
            "description": "Desc" if i < n * with_desc else "",
            "source_page": page,
        })
    return out


SOURCES = [config.catalog_source("m6a"), config.catalog_source("m6b"), config.AAGS_SOURCE]
