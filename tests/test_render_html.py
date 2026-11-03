"""HTML invoice: the room renders a preview with a real Chromium and reads its net log. Runs only where a Chromium is
available (the VM image; on a Mac set CLEANROOM_CHROME to Google Chrome). No walls here: on a laptop the page's
requests fail because collect.attacker.example is a reserved name that resolves nowhere."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import sandbox  # noqa: E402

CHROME = os.environ.get("CLEANROOM_CHROME", "")


def local(room, work, caps):
    return [sys.executable, "-I", os.path.join(work, "runner.py"), work]


@unittest.skipUnless(CHROME and os.path.exists(CHROME), "needs a Chromium (set CLEANROOM_CHROME)")
class RenderHtml(unittest.TestCase):
    def test_page_attempts_land_in_the_receipt(self):
        with open(os.path.join(ROOT, "demo", "inbox", "wasatch_valve_WVS-3310_TESTFILE.html"), "rb") as f:
            data = f.read()
        step = "def extract(p):\n    return {'text': open(p, 'rb').read().decode()}\n"
        r = sandbox.run(data, step, sandbox.Caps(seconds=40), cmd_for=local, render_html=True)
        urls = [a["detail"] for a in r.attempts if a["what"] == "browser"]
        self.assertTrue(any("collect.attacker.example/pixel.png" in u for u in urls), r.attempts)
        self.assertTrue(any("collect.attacker.example/?d=" in u for u in urls), r.attempts)
        self.assertIn("TOTAL DUE $418.20", r.result["text"])


if __name__ == "__main__":
    unittest.main()
