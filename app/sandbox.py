"""Orchestrator side of the clean room: start a throwaway container, run one step on one file, destroy it.

The walls (all enforced by Docker + gVisor, not by our code):
  --runtime=runsc        gVisor user-space kernel between the file and the host
  --network=none         no network at all
  --read-only + tmpfs    nothing persists; 64 MB scratch
  --memory / --cpus / --pids-limit   resource caps
  --cap-drop=ALL, no-new-privileges, nobody user
  no -e flags            no environment from the host: there are no secrets to read
  timeout + docker rm -f the container is destroyed whatever happens
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

IMAGE = os.environ.get("CLEANROOM_IMAGE", "cleanroom-runner:1")
RUNTIME = os.environ.get("CLEANROOM_RUNTIME", "runsc")
RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sandbox", "runner.py")


@dataclass
class Caps:
    memory_mb: int = 512
    cpus: float = 1.0
    pids: int = 128
    seconds: int = 30
    tmpfs_mb: int = 64


@dataclass
class Receipt:
    room: str
    image: str
    runtime: str
    caps: dict
    network: str = "none"
    secrets_inside: int = 0
    started: float = 0.0
    destroyed: float = 0.0
    exit_code: Optional[int] = None
    killed_by: str = ""                       # "", "timeout", "memory"
    attempts: List[dict] = field(default_factory=list)
    result: Optional[dict] = None
    error: str = ""

    def as_dict(self):
        return asdict(self)


def docker_cmd(room: str, workdir: str, caps: Caps) -> List[str]:
    return ["docker", "run", "--rm", "--name", room, f"--runtime={RUNTIME}",
            "--network=none", "--read-only", f"--tmpfs=/tmp:size={caps.tmpfs_mb}m",
            f"--memory={caps.memory_mb}m", f"--memory-swap={caps.memory_mb}m", f"--cpus={caps.cpus}",
            f"--pids-limit={caps.pids}", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=65534:65534", "-v", f"{workdir}:/in:ro", IMAGE, "python3", "-I", "/in/runner.py"]


def parse_lines(out: str, r: Receipt) -> None:
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("ev") == "attempt":
            r.attempts.append({k: ev[k] for k in ("what", "detail", "t") if k in ev})
        elif ev.get("ev") == "result":
            r.result = {k: ev.get(k) for k in ("fields", "text", "notes")}
        elif ev.get("ev") == "error":
            r.error = ev.get("error", "")


NETLOG = os.path.join(os.path.dirname(RUNNER), "netlog.py")


def run(file_bytes: bytes, step_code: str, caps: Caps = Caps(), cmd_for=docker_cmd, render_html: bool = False) -> Receipt:
    room = "cr-" + uuid.uuid4().hex[:12]
    r = Receipt(room=room, image=IMAGE, runtime=RUNTIME, caps=asdict(caps))
    work = tempfile.mkdtemp(prefix=room + "-")
    try:
        with open(os.path.join(work, "file"), "wb") as f:
            f.write(file_bytes)
        with open(os.path.join(work, "step.py"), "w") as f:
            f.write(step_code)
        shutil.copy(RUNNER, os.path.join(work, "runner.py"))
        shutil.copy(NETLOG, os.path.join(work, "netlog.py"))
        if render_html:
            open(os.path.join(work, "render_html"), "w").close()
        # the container runs as nobody (65534): it must be able to read these, and nothing more
        os.chmod(work, 0o755)
        for n in os.listdir(work):
            os.chmod(os.path.join(work, n), 0o444)
        r.started = time.time()
        try:
            p = subprocess.run(cmd_for(room, work, caps), capture_output=True, text=True, timeout=caps.seconds)
            r.exit_code = p.returncode
            if p.returncode == 137:
                r.killed_by = "memory"
            parse_lines(p.stdout, r)
        except subprocess.TimeoutExpired as e:
            r.killed_by = "timeout"
            parse_lines((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), r)
    finally:
        subprocess.run(["docker", "rm", "-f", room], capture_output=True) if cmd_for is docker_cmd else None
        shutil.rmtree(work, ignore_errors=True)
        r.destroyed = time.time()
    return r
