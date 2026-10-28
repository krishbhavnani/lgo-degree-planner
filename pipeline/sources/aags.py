"""EECS AAGS approved-subject list (eecsis.mit.edu) -> AAGS extract.

The AAGS page is the only source of truth for AAGS status.
"""

import re


def parse(page):
    """Return {course_number: status} from color coding, for EVERY subject on the
    AAGS page (any department — e.g. the 6.C51 co-requisite modules like 15.C51).
    The AAGS page is the only source of truth for AAGS status.

    blue  -> Approved-Offered, grey -> Approved-NotThisYear,
    black -> Approved-NotInCatalog (in AAGS list but absent from catalog).
    """
    status = {}
    # Each course link carries an inline color style and a search=NUMBER href.
    for m in re.finditer(r'style="[^"]*color:(blue|grey|black)[^"]*"[^>]*href="[^"]*search=([A-Za-z0-9]+\.[A-Za-z0-9]+)"',
                         page):
        color, num = m.group(1), m.group(2)
        status[num] = color
    # Some pages place href before style; try the reverse order too.
    for m in re.finditer(r'href="[^"]*search=([A-Za-z0-9]+\.[A-Za-z0-9]+)"[^>]*style="[^"]*color:(blue|grey|black)',
                         page):
        num, color = m.group(1), m.group(2)
        status.setdefault(num, color)
    label = {"blue": "Approved-Offered", "grey": "Approved-NotThisYear",
             "black": "Approved-NotInCatalog"}
    return {num: label[c] for num, c in status.items()}


def extract(page):
    status = parse(page)
    return {"records": [{"number": n, "status": s} for n, s in sorted(status.items())],
            "problems": []}
