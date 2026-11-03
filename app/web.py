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

from . import agent, devmode, flags

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "demo", "inbox")
MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="Clean Room Intake")
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
    if file is not None:
        return {"id": _start(file.filename or "file", await file.read())}
    b = await req.json()
    name = os.path.basename(str(b.get("sample", "")))
    path = os.path.join(INBOX, name)
    if not name or not os.path.isfile(path):
        raise HTTPException(404, "No such sample.")
    with open(path, "rb") as f:
        return {"id": _start(name, f.read())}


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
                 "stopped": _stopped(j)}
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
