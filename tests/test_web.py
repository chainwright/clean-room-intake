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
    def __init__(self, fields, text=None):
        self.fields, self.text = fields, text

    def __call__(self, system, user):
        if system.startswith("You write"):
            if self.text is not None:           # a step that returns the invoice's real text, as the model's would
                return f"def extract(path):\n    return {{'text': {self.text!r}}}\n"
            return "def extract(path):\n    return {'text': open(path,'rb').read().decode('latin-1')}\n"
        return json.dumps(self.fields)


class Web(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(web.app)
        web.JOBS.clear()
        self._run = agent.run

    def tearDown(self):
        agent.run = self._run

    def use(self, fields, text=None):
        agent.run = lambda name, data, **kw: self._run(name, data, llm=Fake(fields, text), cmd_for=local,
                                                         caps=sandbox.Caps(seconds=10), on_state=kw.get("on_state"))

    def wait(self, jid):
        for _ in range(100):
            j = self.c.get(f"/api/intake/{jid}").json()
            if j["done"]:
                return j
            time.sleep(0.05)
        self.fail("not done")

    def test_bank_change_email_is_held_until_controller_approves(self):
        self.use({"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0,
                  "bank": {"routing": "000098765", "account_last4": "9013"}},
                 "Granite Peak Refrigerants INVOICE GPR-5561 TOTAL $1,236.00 Summit Ridge Bank routing 000098765 account ****9013")
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
        self.use({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24117", "total": 736.81,
                  "bank": {"routing": "000012345", "account_last4": "4471"}},
                 "Bonneville Sheet Metal Supply INVOICE BSM-24117 Total $736.81 Mountain Ledger Bank routing 000012345 account ****4471")
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


class Control(unittest.TestCase):
    """The outside check must never become a way out for a stranger's file."""

    def setUp(self):
        self.calls = []
        self._open = web.urllib.request.OpenerDirector.open
        web.urllib.request.OpenerDirector.open = lambda me, url, timeout=None: self.calls.append(url) or (_ for _ in ()).throw(OSError("x"))

    def tearDown(self):
        web.urllib.request.OpenerDirector.open = self._open

    def att(self, url):
        return {"what": "browser", "detail": f"{url} (ERR_NAME_NOT_RESOLVED)"}

    def test_strangers_file_gets_no_outside_check(self):
        self.assertEqual(web.control("invoice.html", [self.att("https://example.com/x")]), [])
        self.assertEqual(self.calls, [])

    def test_only_allowlisted_hosts_even_for_our_test_file(self):
        out = web.control("wasatch_valve_WVS-3310_TESTFILE.html",
                          [self.att("http://169.254.169.254/latest"), self.att("https://evil.example/p"),
                           self.att("https://example.com/pixel.png?i=1"), self.att("https://1.1.1.1/t?d=x")])
        self.assertEqual([c["host"] for c in out], ["https://example.com", "https://1.1.1.1"])
        self.assertEqual(self.calls, ["https://example.com/", "https://1.1.1.1/"])   # bare host, nothing from the file



class FailClosed(unittest.TestCase):
    """The hold doesn't trust the model: it is checked against the room's own text."""
    TXT = "Granite Peak Refrigerants INVOICE GPR-5561 TOTAL $1,236.00 Summit Ridge Bank routing 000098765 account ****9013"

    def test_talked_into_the_old_account_still_holds(self):
        # the model was persuaded to report the vendor's OLD bank details; the text says otherwise
        f = web.flags.check({"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0,
                             "bank": {"routing": "000067890", "account_last4": "2208"}}, text=self.TXT)
        codes = [x["code"] for x in f]
        self.assertIn("bank_changed", codes)             # 000098765 is in the text and isn't the known routing
        self.assertIn("not_in_text", codes)              # and the reported old routing isn't in the file at all

    def test_hidden_instructions_hold(self):
        f = web.flags.check({"vendor": "Jordan River Plumbing Co.", "invoice_no": "JRP-7781", "total": 2940.0},
                            text="JRP-7781 TOTAL DUE $2,940.00", notes=["Hidden instructions found inside the document. ..."])
        self.assertEqual([x["code"] for x in f], ["hidden_instructions"])

    def test_new_vendor_with_bank_details_holds(self):
        f = web.flags.check({"vendor": "Someone New LLC", "invoice_no": "N-1", "total": 10.0, "pay_method": "ach",
                             "bank": {"routing": "000011111", "account_last4": "1111"}},
                            text="Someone New LLC N-1 $10.00 routing 000011111 ****1111")
        self.assertEqual([x["code"] for x in f], ["new_vendor"])

    def test_known_vendor_same_bank_pays(self):
        self.assertEqual(web.flags.check({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24117", "total": 736.81,
                                          "bank": {"routing": "000012345", "account_last4": "4471"}},
                                         text="BSM-24117 $736.81 routing 000012345 ****4471"), [])
