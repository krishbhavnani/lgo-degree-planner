"""Polite HTTP fetching: identifying user agent, per-host delay, retries, curl fallback.

Some machines (e.g. a Mac with python.org Python) can't verify MIT's certificate chain
with urllib. When that happens we switch to the system `curl`, which uses the OS trust store.
"""

import os
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from . import config


class FetchResult:
    def __init__(self, url, status, body, final_url=None, error=None, via="urllib",
                 fetched_at=None):
        self.url = url
        self.status = status            # HTTP status, or None if no response at all
        self.body = body or b""         # raw bytes, exactly as served
        self.final_url = final_url or url
        self.error = error              # text, when the fetch failed
        self.via = via                  # "urllib" | "curl" | "cache"
        self.fetched_at = fetched_at or datetime.now(timezone.utc)

    @property
    def ok(self):
        return self.status == 200 and not self.error

    def text(self):
        return self.body.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, user_agent=config.USER_AGENT, min_delay=config.MIN_DELAY_PER_HOST,
                 retries=config.RETRIES, backoff=config.BACKOFF, timeout=config.TIMEOUT,
                 sleep=time.sleep, log=print):
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self.sleep = sleep
        self.log = log
        self._last = {}                 # host -> monotonic time of last request
        self._use_curl = set()          # hosts where urllib failed SSL verification

    def _wait_turn(self, host):
        last = self._last.get(host)
        if last is not None:
            gap = time.monotonic() - last
            if gap < self.min_delay:
                self.sleep(self.min_delay - gap)
        self._last[host] = time.monotonic()

    def get(self, url):
        host = urlparse(url).hostname or ""
        attempt, delay = 0, self.backoff
        while True:
            self._wait_turn(host)
            if host in self._use_curl:
                res = self._curl(url)
            else:
                res = self._urllib(url)
                if res.error == "ssl":
                    self.log("  (urllib can't verify %s's certificate; using curl)" % host)
                    self._use_curl.add(host)
                    res = self._curl(url)
            retryable = res.status is None or (res.status is not None and res.status >= 500)
            if not retryable or attempt >= self.retries:
                return res
            attempt += 1
            self.log("  retry %d/%d for %s (%s) in %.0fs" %
                     (attempt, self.retries, url, res.error or res.status, delay))
            self.sleep(delay)
            delay *= 2

    def _urllib(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return FetchResult(url, resp.status, resp.read(), final_url=resp.geturl())
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            return FetchResult(url, e.code, body, final_url=e.geturl() or url,
                               error="HTTP %d" % e.code)
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError) or \
                    "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
                return FetchResult(url, None, b"", error="ssl")
            return FetchResult(url, None, b"", error="network: %s" % e.reason)
        except (socket.timeout, TimeoutError) as e:
            return FetchResult(url, None, b"", error="timeout: %s" % e)
        except OSError as e:
            return FetchResult(url, None, b"", error="network: %s" % e)

    def _curl(self, url):
        fd, path = tempfile.mkstemp(prefix="lgo-dp-")
        os.close(fd)
        try:
            proc = subprocess.run(
                ["curl", "-sS", "-L", "--max-time", str(self.timeout), "-A", self.user_agent,
                 "-o", path, "-w", "%{http_code}\t%{url_effective}", url],
                capture_output=True, text=True)
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return FetchResult(url, None, b"", error="curl not installed", via="curl")
        finally:
            if os.path.exists(path):
                os.remove(path)
        code, _, final = proc.stdout.partition("\t")
        status = int(code) if code.isdigit() and code != "000" else None
        error = None
        if proc.returncode != 0:
            error = "curl exit %d: %s" % (proc.returncode, proc.stderr.strip()[:200])
        elif status != 200:
            error = "HTTP %s" % status
        return FetchResult(url, status, body, final_url=final or url, error=error, via="curl")
