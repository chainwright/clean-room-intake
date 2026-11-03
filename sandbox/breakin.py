"""Break-in test: OUR OWN attack script, run as the step inside a fresh room with exactly the same walls a stranger's
file gets. Nothing here is aimed at anyone else: every target is the room itself, or a public address the room
should not be able to reach.

Each attack prints one line as it happens: {"ev": "probe", "attack": ..., "how": ..., "outcome": ..., "held": bool}
"held" is decided by what actually happened, not assumed: if a wall let something through, the line says so.
The memory attack goes last because it is meant to get the whole room killed; the orchestrator reports that part
from outside (exit 137).
"""
import json
import os
import socket
import sys
import time

T0 = time.monotonic()


def probe(attack, how, outcome, held):
    sys.__stdout__.write(json.dumps({"ev": "probe", "attack": attack, "how": how, "outcome": outcome, "held": held,
                                     "t": round(time.monotonic() - T0, 3)}) + "\n")
    sys.__stdout__.flush()


def secrets():
    names = [k for k in list(os.environ.keys()) if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASS", "VULTR"))]
    key = os.environ.get("VULTR_INFERENCE_KEY")
    if names or key:
        probe("read the API key", "search the environment for keys and tokens", f"found {', '.join(names) or 'a key'}", False)
    else:
        probe("read the API key", "search the environment for keys and tokens",
              f"nothing there · the room only has {', '.join(sorted(os.environ.keys()))}", True)


def host_files():
    got = []
    for p in ("/etc/shadow", "/root/.ssh/id_ed25519", "/etc/cleanroom.env"):
        try:
            with open(p) as f:
                got.append((p, len(f.read())))
        except OSError as e:
            got.append((p, type(e).__name__))
    leaked = [p for p, r in got if isinstance(r, int) and r > 0]
    probe("read password and key files", "open /etc/shadow, root's ssh key, the app's key file",
          f"read {', '.join(leaked)}" if leaked else "; ".join(f"{p}: {r}" for p, r in got), not leaked)


def write_root():
    try:
        with open("/payload.sh", "w") as f:
            f.write("echo hi\n")
        probe("leave something behind", "write /payload.sh", "written", False)
    except OSError as e:
        probe("leave something behind", "write /payload.sh", f"refused · {e.strerror or type(e).__name__}", True)


def dns():
    try:
        socket.getaddrinfo("example.com", 443)
        probe("call home by name", "look up example.com", "resolved", False)
    except OSError as e:
        probe("call home by name", "look up example.com", f"no answer · {type(e).__name__}", True)


def raw_ip():
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        probe("call home by IP", "connect to 1.1.1.1:443", "connected", False)
    except OSError as e:
        probe("call home by IP", "connect to 1.1.1.1:443", f"no route · {e.strerror or type(e).__name__}", True)


def root():
    try:
        os.setuid(0)
        probe("become root", "setuid(0)", "became root", False)
        return
    except OSError as e:
        why = e.strerror or type(e).__name__
    cap = "?"
    try:
        cap = next(l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff"))
    except Exception:
        pass
    probe("become root", "setuid(0), then check capabilities", f"refused · {why} · capabilities {cap}",
          cap.strip("0") == "")


def flood():
    """Second room: a fork flood. Each child sleeps and exits; the room's caps decide how far it gets. The count is
    read from outside too (the audit hook records every fork), because the flood is expected to end the room."""
    probe("flood with processes", "start 500 processes", "starting…", None)
    kids, err = [], ""
    for _ in range(500):
        try:
            pid = os.fork()
        except OSError as e:
            err = e.strerror or type(e).__name__
            break
        if pid == 0:
            time.sleep(3)
            os._exit(0)
        kids.append(pid)
    probe("flood with processes", "start 500 processes",
          f"stopped at {len(kids)} · {err}" if err else "started all 500", bool(err))
    for k in kids:
        try:
            os.waitpid(k, 0)
        except OSError:
            pass


def memory():
    probe("eat the memory", "grab 1 GB, 64 MB at a time", "allocating…", None)   # the outcome comes from outside
    hog = []
    for _ in range(16):
        hog.append(bytearray(64 * 1024 * 1024))
    probe("eat the memory", "grab 1 GB, 64 MB at a time", "got 1 GB", False)


def extract(path):
    """The orchestrator hands in one word: "flood" for the second room, anything else for the first."""
    mode = open(path).read().strip()
    attacks = (flood,) if mode == "flood" else (secrets, host_files, write_root, dns, raw_ip, root, memory)
    for attack in attacks:
        try:
            attack()
        except MemoryError:
            probe("eat the memory", "grab 1 GB, 64 MB at a time", "refused · MemoryError", True)
        except Exception as e:      # an attack that crashes is reported as such, never as "held"
            probe(attack.__name__, "", f"crashed · {type(e).__name__}: {e}"[:200], None)
    return {"fields": {}, "text": "break-in test finished", "notes": []}
