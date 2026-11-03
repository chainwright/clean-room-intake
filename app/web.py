"""HTTP API for the clerk (Intake) and the controller (Receipts). One process on the Vultr VM.

POST /api/intake            multipart file, or {"sample": "<name>"}  -> {"id"}
GET  /api/intake/{id}       live state, fields, flags, receipts
GET  /api/intakes           the queue, newest first
POST /api/intake/{id}/pay   clerk: send to pay list (refused while a blocking flag isn't approved)
POST /api/intake/{id}/approve   controller approves the flags
GET  /api/samples           the demo inbox (fictional files, incl. our harmless trap)
"""
from __future__ import annotations

import email
import os
import re
import threading
import time
import uuid
from email import policy
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import agent, devmode, flags, sandbox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "demo", "inbox")
MAX_BYTES = 10 * 1024 * 1024
# A public demo must not be farmed: each visitor gets a fair share per hour, the site has a daily ceiling,
# and only a few rooms run at once (the VM has 2 vCPU). A visitor over a limit gets a plain sentence.
PER_IP_PER_HOUR = int(os.environ.get("CLEANROOM_PER_IP_PER_HOUR", "30"))
PER_DAY = int(os.environ.get("CLEANROOM_PER_DAY", "600"))
MAX_RUNNING = int(os.environ.get("CLEANROOM_MAX_RUNNING", "4"))
_quota = {"hour": "", "ip": {}, "day": "", "n": 0}

app = FastAPI(title="Clean Room Intake")


@app.middleware("http")
async def no_stale_ui(request, call_next):
    """The page and its script revalidate on every load, so a deploy is seen at once (judges, video takes)."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp
JOBS: dict = {}
LOCK = threading.Lock()


def _unwrap_email(name: str, data: bytes):
    """An .eml is opened for its sender and attachment only; the attachment goes to the clean room like any file."""
    msg = email.message_from_bytes(data, policy=policy.default)
    sender = str(msg.get("From", ""))
    for part in msg.iter_attachments():
        return part.get_filename() or "attachment", part.get_content(), sender
    return name, data, sender


def _work(job_id: str, name: str, data: bytes, sender: str):
    job = JOBS[job_id]

    def on_state(s):
        with LOCK:
            job["states"].append({"state": s, "at": time.time()})
            job["state"] = s

    try:
        if devmode.ON:   # laptop UI work only: no walls, scripted model (see devmode.py)
            it = agent.run(name, data, llm=devmode.fake_llm, cmd_for=devmode.local_cmd, on_state=on_state)
        else:
            it = agent.run(name, data, on_state=on_state)
        f = flags.check(it.fields, sender=sender or None)
        with LOCK:
            job.update(kind=it.kind, fields=it.fields, text=it.text, notes=it.flags,
                       flags=f, hold=flags.hold_text(f, (it.fields or {}).get("vendor", "")),
                       tries=it.tries, error=it.error, done=True)
    except Exception as e:   # the clean room must never take the app down
        with LOCK:
            job.update(error=f"{type(e).__name__}: {e}"[:300], state="failed", done=True)


def _visitor(req: Request) -> str:
    """Who is asking. Behind Caddy (on this VM) the socket is 127.0.0.1 and Caddy writes the real client into
    X-Forwarded-For, replacing anything the client sent; from anywhere else the header is ignored."""
    host = req.client.host if req.client else "?"
    if host in ("127.0.0.1", "::1"):
        return req.headers.get("x-forwarded-for", "").split(",")[0].strip() or host
    return host


def _admit(ip: str) -> None:
    now = time.gmtime()
    h, d = time.strftime("%Y%m%d%H", now), time.strftime("%Y%m%d", now)
    with LOCK:
        if _quota["hour"] != h:
            _quota.update(hour=h, ip={})
        if _quota["day"] != d:
            _quota.update(day=d, n=0)
        running = sum(1 for j in JOBS.values() if not j["done"])
        if running >= MAX_RUNNING:
            raise HTTPException(429, "A few rooms are open right now. Try again in a few seconds.")
        if _quota["ip"].get(ip, 0) >= PER_IP_PER_HOUR:
            raise HTTPException(429, "That's a lot of files from you this hour. Try again later.")
        if _quota["n"] >= PER_DAY:
            raise HTTPException(429, "The demo has opened its daily share of files. Try again tomorrow.")
        _quota["ip"][ip] = _quota["ip"].get(ip, 0) + 1
        _quota["n"] += 1


def _start(name: str, data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files up to 10 MB.")
    sender = ""
    if name.lower().endswith(".eml"):
        name, data, sender = _unwrap_email(name, data)
    jid = uuid.uuid4().hex[:10]
    with LOCK:
        JOBS[jid] = {"id": jid, "file": name, "sender": sender, "state": "queued", "states": [{"state": "queued", "at": time.time()}],
                     "fields": {}, "flags": [], "notes": [], "tries": [], "done": False, "paid": False,
                     "approved": False, "created": time.time()}
    threading.Thread(target=_work, args=(jid, name, data, sender), daemon=True).start()
    return jid


@app.post("/api/intake")
async def intake(req: Request, file: Optional[UploadFile] = File(default=None)):
    _admit(_visitor(req))
    if file is not None:
        return {"id": _start(file.filename or "file", await file.read())}
    b = await req.json()
    name = os.path.basename(str(b.get("sample", "")))
    path = os.path.join(INBOX, name)
    if not name or not os.path.isfile(path):
        raise HTTPException(404, "No such sample.")
    with open(path, "rb") as f:
        return {"id": _start(name, f.read())}


BREAKIN = os.path.join(ROOT, "sandbox", "breakin.py")


def settle(rooms: list) -> list:
    """Attacks meant to get a room killed (memory, process flood) are judged from outside: the room's exit code and
    the forks its own audit hook recorded, not a promise from inside. Repeated lines for one attack collapse to the
    last word on it."""
    last = {}
    for r in rooms:
        for p in r["probes"]:
            last[p["attack"]] = dict(p, room=r["room"])
    out = list(last.values())
    by_room = {r["room"]: r for r in rooms}
    for p in out:
        r = by_room[p["room"]]
        ended = r.get("exit_code") not in (0, None) or bool(r.get("killed_by"))
        if p["attack"] == "eat the memory" and p["held"] is None:
            killed = r.get("killed_by") == "memory" or r.get("exit_code") == 137
            p.update(outcome=f"room killed at {r['caps']['memory_mb']} MB (exit 137)" if killed
                     else "the room was not killed", held=killed)
        if p["attack"] == "flood the server" and p["held"] is None:
            forks = sum(1 for a in r["attempts"] if a.get("what") == "os.fork")
            p.update(outcome=f"room stopped after {forks} processes (exit {r.get('exit_code')})" if ended
                     else f"{forks} processes, room still up", held=ended and forks < 500)
    return out


def _breakin_work(job_id: str):
    job = JOBS[job_id]

    def state(s):
        with LOCK:
            job["states"].append({"state": s, "at": time.time()})
            job["state"] = s

    try:
        code = open(BREAKIN).read()
        rooms, tries = [], []
        for word in (b"walls", b"flood"):              # two fresh rooms: each of the two big attacks ends its room
            state("sandbox_up"); state("opening")
            if devmode.ON:
                rec = sandbox.run(word, code, sandbox.Caps(seconds=20), cmd_for=devmode.local_cmd)
            else:
                rec = sandbox.run(word, code)
            r = rec.as_dict()
            rooms.append(r); tries.append({"step": code, "receipt": r})
            state("breakin")
        probes = settle(rooms)
        state("destroyed")
        with LOCK:
            job.update(kind="breakin", tries=tries, probes=probes, done=True, fields={},
                       error="" if probes else "the test didn't report back")
    except Exception as e:
        with LOCK:
            job.update(error=f"{type(e).__name__}: {e}"[:300], state="failed", done=True)


@app.post("/api/breakin")
async def breakin(req: Request):
    """Run our own attack script in a fresh room with the same walls. No model involved."""
    _admit(_visitor(req))
    jid = uuid.uuid4().hex[:10]
    with LOCK:
        JOBS[jid] = {"id": jid, "file": "break-in test (our attack script)", "sender": "", "state": "queued",
                     "states": [{"state": "queued", "at": time.time()}], "fields": {}, "flags": [], "notes": [],
                     "tries": [], "probes": [], "done": False, "paid": False, "approved": False,
                     "created": time.time(), "kind": "breakin"}
    threading.Thread(target=_breakin_work, args=(jid,), daemon=True).start()
    return {"id": jid}


@app.get("/api/intake/{jid}")
def get_intake(jid: str):
    with LOCK:
        if jid not in JOBS:
            raise HTTPException(404)
        return JSONResponse(JOBS[jid])


def _stopped(j) -> int:
    """How many distinct things the file tried (one network target counts once, however many calls it took)."""
    seen = set()
    for t in j["tries"]:
        for a in t["receipt"]["attempts"]:
            if a["what"].startswith("socket") or a["what"] == "urllib.Request":
                m = re.search(r"https?://([^/'\"]+)", a["detail"]) or re.search(r"\('([^']+)'", a["detail"])
                seen.add(("net", m.group(1) if m else a["detail"]))
            else:
                seen.add((a["what"], a["detail"]))
    return len(seen)


@app.get("/api/intakes")
def list_intakes():
    with LOCK:
        return [{k: j[k] for k in ("id", "file", "state", "done", "paid", "approved", "created")} |
                {"vendor": (j["fields"] or {}).get("vendor"), "total": (j["fields"] or {}).get("total"),
                 "flagged": bool(j["flags"]), "blocked": any(t["receipt"]["attempts"] for t in j["tries"]),
                 "stopped": _stopped(j), "kind": j.get("kind", ""),
                 "held": sum(1 for p in j.get("probes", []) if p.get("held")), "probes": len(j.get("probes", []))}
                for j in sorted(JOBS.values(), key=lambda j: -j["created"])]


@app.post("/api/intake/{jid}/approve")
def approve(jid: str):
    with LOCK:
        j = JOBS.get(jid) or {}
        if not j:
            raise HTTPException(404)
        j["approved"] = True
        return {"ok": True}


@app.post("/api/intake/{jid}/pay")
def pay(jid: str):
    with LOCK:
        j = JOBS.get(jid)
        if not j:
            raise HTTPException(404)
        if any(f.get("blocks") for f in j["flags"]) and not j["approved"]:
            raise HTTPException(409, "On hold: the controller has to approve the flags first.")
        j["paid"] = True
        return {"ok": True}


@app.get("/api/samples")
def samples():
    return sorted(os.listdir(INBOX))


WEB = os.path.join(ROOT, "web")
if os.path.isdir(WEB):
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
