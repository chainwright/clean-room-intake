"""Chromium net-log parsing, on a real log from headless Chrome rendering an HTML invoice with a tracking pixel and a
fetch() to collect.attacker.example (reserved name, resolves nowhere). Fixture trimmed to the page's own requests."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sandbox"))
import netlog  # noqa: E402


class NetLog(unittest.TestCase):
    def test_page_attempts_with_chromium_errors(self):
        a = netlog.attempts(os.path.join(ROOT, "tests", "fixtures_chrome_netlog.json"))
        self.assertEqual([x["url"] for x in a], ["https://collect.attacker.example/pixel.png?i=WVS-3310",
                                                  "https://collect.attacker.example/?d="])
        self.assertTrue(all(x["error"] == "ERR_NAME_NOT_RESOLVED" for x in a))


if __name__ == "__main__":
    unittest.main()
