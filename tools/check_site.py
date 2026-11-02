#!/usr/bin/env python3
"""Check a staged site folder before it is deployed: every local file index.html loads must be there.

    python3 tools/check_site.py _site

Exits 1 and lists what's missing, so a deploy can't ship a page that loads a file it doesn't have.
External URLs and the optional personal/ overlay are skipped.
"""

import os
import re
import sys


def missing_files(site_dir):
    with open(os.path.join(site_dir, "index.html"), encoding="utf-8") as f:
        html = f.read()
    refs = re.findall(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+)"', html)
    local = [r for r in refs if not r.startswith(("http:", "https:", "//", "personal/"))]
    return [r for r in local if not os.path.isfile(os.path.join(site_dir, r))]


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "_site"
    missing = missing_files(site)
    for r in missing:
        print("missing from %s: %s" % (site, r))
    sys.exit(1 if missing else 0)
