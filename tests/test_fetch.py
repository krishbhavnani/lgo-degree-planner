import unittest

from pipeline.fetch import Fetcher, FetchResult

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

    def test_polite_delay_between_same_host_requests(self):
        f = StubFetcher([ok(), ok()])
        f.get(URL)
        f.get(URL)
        self.assertTrue(f.sleeps and 0 < f.sleeps[0] <= 1.5)


if __name__ == "__main__":
    unittest.main()
