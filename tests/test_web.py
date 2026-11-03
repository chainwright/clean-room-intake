import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient  # noqa: E402

from app import agent, sandbox, web  # noqa: E402


def local(room, work, caps):
    return [sys.executable, "-I", os.path.join(work, "runner.py"), work]


class Fake:
    def __init__(self, fields):
        self.fields = fields

    def __call__(self, system, user):
        if system.startswith("You write"):
            return "def extract(path):\n    return {'text': open(path,'rb').read().decode('latin-1')}\n"
        return json.dumps(self.fields)


class Web(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(web.app)
        web.JOBS.clear()
        self._run = agent.run

    def tearDown(self):
        agent.run = self._run

    def use(self, fields):
        agent.run = lambda name, data, **kw: self._run(name, data, llm=Fake(fields), cmd_for=local,
                                                         caps=sandbox.Caps(seconds=10), on_state=kw.get("on_state"))

    def wait(self, jid):
        for _ in range(100):
            j = self.c.get(f"/api/intake/{jid}").json()
            if j["done"]:
                return j
            time.sleep(0.05)
        self.fail("not done")

    def test_bank_change_email_is_held_until_controller_approves(self):
        self.use({"vendor": "Granite Peak Refrigerants", "total": 1236.0,
                  "bank": {"routing": "000098765", "account_last4": "9013"}})
        jid = self.c.post("/api/intake", json={"sample": "granite_peak_GPR-5561.eml"}).json()["id"]
        j = self.wait(jid)
        self.assertEqual(j["file"], "GPR-5561.docx")                       # the attachment, unwrapped
        self.assertIn("example.net", j["sender"])
        self.assertEqual([f["code"] for f in j["flags"]], ["bank_changed", "sender_domain"])
        self.assertEqual(self.c.post(f"/api/intake/{jid}/pay").status_code, 409)
        self.c.post(f"/api/intake/{jid}/approve")
        self.assertEqual(self.c.post(f"/api/intake/{jid}/pay").status_code, 200)
        self.assertEqual(j["states"][-1]["state"], "destroyed")

    def test_clean_invoice_pays_straight_away(self):
        self.use({"vendor": "Bonneville Sheet Metal Supply", "total": 736.81,
                  "bank": {"routing": "000012345", "account_last4": "4471"}})
        jid = self.c.post("/api/intake", json={"sample": "bonneville_BSM-24117.pdf"}).json()["id"]
        self.wait(jid)
        self.assertEqual(self.c.post(f"/api/intake/{jid}/pay").status_code, 200)

    def test_samples_and_path_traversal(self):
        self.assertIn("jordan_river_JRP-7781_TESTFILE.docx", self.c.get("/api/samples").json())
        self.assertEqual(self.c.post("/api/intake", json={"sample": "../../app/web.py"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()


class Quota(unittest.TestCase):
    """The public demo can't be farmed: per-visitor hourly share, daily ceiling, a few rooms at once."""

    def setUp(self):
        web.JOBS.clear()
        web._quota.update(hour="", ip={}, day="", n=0)
        self.saved = (web.PER_IP_PER_HOUR, web.PER_DAY, web.MAX_RUNNING)

    def tearDown(self):
        web.PER_IP_PER_HOUR, web.PER_DAY, web.MAX_RUNNING = self.saved
        web.JOBS.clear()

    def test_hourly_share_per_visitor(self):
        web.PER_IP_PER_HOUR, web.PER_DAY, web.MAX_RUNNING = 2, 100, 100
        web._admit("1.1.1.1"); web._admit("1.1.1.1")
        with self.assertRaises(web.HTTPException) as e:
            web._admit("1.1.1.1")
        self.assertEqual(e.exception.status_code, 429)
        web._admit("2.2.2.2")   # someone else still gets in

    def test_daily_ceiling(self):
        web.PER_IP_PER_HOUR, web.PER_DAY, web.MAX_RUNNING = 100, 2, 100
        web._admit("1.1.1.1"); web._admit("2.2.2.2")
        with self.assertRaises(web.HTTPException):
            web._admit("3.3.3.3")

    def test_rooms_at_once(self):
        web.PER_IP_PER_HOUR, web.PER_DAY, web.MAX_RUNNING = 100, 100, 1
        web.JOBS["x"] = {"done": False}
        with self.assertRaises(web.HTTPException) as e:
            web._admit("1.1.1.1")
        self.assertIn("rooms are open", e.exception.detail)
        web.JOBS["x"]["done"] = True
        web._admit("1.1.1.1")


class Visitor(unittest.TestCase):
    def req(self, host, xff=""):
        from starlette.requests import Request
        h = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "client": (host, 1), "headers": h, "method": "POST", "path": "/"})

    def test_behind_caddy_uses_forwarded_client(self):
        self.assertEqual(web._visitor(self.req("127.0.0.1", "203.0.113.7")), "203.0.113.7")

    def test_direct_client_cannot_spoof(self):
        self.assertEqual(web._visitor(self.req("198.51.100.4", "1.2.3.4")), "198.51.100.4")


class BreakIn(unittest.TestCase):
    """Outcomes of the attacks that end a room are read from outside, never assumed."""

    def room(self, name, exit_code, killed_by="", probes=(), forks=0):
        return {"room": name, "exit_code": exit_code, "killed_by": killed_by, "caps": {"memory_mb": 512},
                "probes": list(probes), "attempts": [{"what": "os.fork"}] * forks}

    def test_memory_counts_only_if_the_room_was_killed(self):
        mem = {"attack": "eat the memory", "how": "", "outcome": "allocating…", "held": None, "t": 0.1}
        held = web.settle([self.room("a", 137, "memory", [mem])])[0]
        self.assertTrue(held["held"]); self.assertIn("exit 137", held["outcome"])
        open_ = web.settle([self.room("a", 0, "", [dict(mem)])])[0]
        self.assertFalse(open_["held"])

    def test_flood_is_counted_from_the_rooms_own_record(self):
        fl = {"attack": "flood with processes", "how": "", "outcome": "starting…", "held": None, "t": 0.1}
        p = web.settle([self.room("b", 2, "", [fl], forks=51)])[0]
        self.assertTrue(p["held"]); self.assertIn("process cap at 51 processes", p["outcome"])
        p = web.settle([self.room("b", 0, "", [dict(fl)], forks=500)])[0]
        self.assertFalse(p["held"])

    def test_a_wall_that_failed_is_shown_as_failed(self):
        got = {"attack": "call home by IP", "how": "", "outcome": "connected", "held": False, "t": 0.1}
        self.assertFalse(web.settle([self.room("a", 0, "", [got])])[0]["held"])
