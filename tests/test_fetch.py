import ssl
import unittest
import urllib.error
from unittest import mock

from pipeline.fetch import Fetcher, FetchResult, tls_context

URL = "https://student.mit.edu/catalog/m6a.html"


class StubFetcher(Fetcher):
    """Fetcher with scripted urllib/curl responses and a recorded (not real) sleep."""

    def __init__(self, urllib_results, curl_results=()):
        self.sleeps = []
        super().__init__(sleep=self.sleeps.append, log=lambda *a: None)
        self.urllib_results = list(urllib_results)
        self.curl_results = list(curl_results)
        self.calls = []

    def _urllib(self, url):
        self.calls.append("urllib")
        return self.urllib_results.pop(0)

    def _curl(self, url):
        self.calls.append("curl")
        return self.curl_results.pop(0)


def ok():
    return FetchResult(URL, 200, b"<html>ok</html>")


class FetchTest(unittest.TestCase):
    def test_retries_5xx_with_backoff(self):
        f = StubFetcher([FetchResult(URL, 503, b"", error="HTTP 503"),
                         FetchResult(URL, None, b"", error="timeout"), ok()])
        self.assertTrue(f.get(URL).ok)
        self.assertEqual(f.calls, ["urllib"] * 3)
        self.assertIn(2.0, f.sleeps)
        self.assertIn(4.0, f.sleeps)

    def test_gives_up_after_retries(self):
        f = StubFetcher([FetchResult(URL, 500, b"", error="HTTP 500")] * 4)
        res = f.get(URL)
        self.assertEqual(res.status, 500)
        self.assertEqual(len(f.calls), 4)

    def test_404_not_retried(self):
        f = StubFetcher([FetchResult(URL, 404, b"", error="HTTP 404")])
        self.assertEqual(f.get(URL).status, 404)
        self.assertEqual(len(f.calls), 1)

    def test_ssl_failure_switches_host_to_curl(self):
        f = StubFetcher([FetchResult(URL, None, b"", error="ssl")], [ok(), ok()])
        self.assertTrue(f.get(URL).ok)
        self.assertTrue(f.get(URL).ok)
        self.assertEqual(f.calls, ["urllib", "curl", "curl"])

    def test_tls_handshake_failure_not_retried(self):
        f = StubFetcher([FetchResult(URL, None, b"", error="tls: dh key too small")])
        self.assertTrue(f.get(URL).error.startswith("tls:"))
        self.assertEqual(f.calls, ["urllib"])

    def test_polite_delay_between_same_host_requests(self):
        f = StubFetcher([ok(), ok()])
        f.get(URL)
        f.get(URL)
        self.assertTrue(f.sleeps and 0 < f.sleeps[0] <= 1.5)



class TlsContextTest(unittest.TestCase):
    def test_legacy_host_allows_old_key_exchange_but_still_verifies(self):
        ctx = tls_context("student.mit.edu")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        if hasattr(ctx, "security_level"):          # Python 3.10+
            self.assertEqual(ctx.security_level, 1)

    def test_other_hosts_use_the_default(self):
        self.assertIsNone(tls_context("mitsloan.mit.edu"))
        self.assertIsNone(tls_context("eecsis.mit.edu"))

    def test_urllib_passes_the_context_and_labels_handshake_errors(self):
        seen = {}

        def fake_urlopen(req, timeout=None, context=None):
            seen["context"] = context
            raise urllib.error.URLError(ssl.SSLError(1, "[SSL: DH_KEY_TOO_SMALL] dh key too small"))

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            res = Fetcher(log=lambda *a: None)._urllib(URL)
        self.assertIsNotNone(seen["context"])
        self.assertTrue(res.error.startswith("tls:"), res.error)


if __name__ == "__main__":
    unittest.main()
