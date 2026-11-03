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
    """Looks where a key could still be even after the runner cleaned the environment: the variables, and the
    environment the room's processes were STARTED with (/proc/self/environ, /proc/1/environ)."""
    names = [k for k in list(os.environ.keys()) if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASS", "VULTR"))]
    key = os.environ.get("VULTR_INFERENCE_KEY")
    for p in ("/proc/self/environ", "/proc/1/environ"):
        try:
            raw = open(p, "rb").read().decode(errors="replace")
        except OSError:
            continue
        names += [kv.split("=", 1)[0] + f" ({p})" for kv in raw.split("\0")
                  if "=" in kv and any(w in kv.split("=", 1)[0].upper() for w in ("KEY", "TOKEN", "SECRET", "PASS", "VULTR"))]
    if names or key:
        probe("read the API key", "search the environment and /proc/*/environ for keys and tokens", f"found {', '.join(names) or 'a key'}", False)
    else:
        probe("read the API key", "search the environment and /proc/*/environ for keys and tokens",
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
    probe("read password and key files", "open /etc/shadow, root's ssh key, the app's key file (as the room sees them)",
          f"read {', '.join(leaked)}" if leaked else "; ".join(f"{p}: {r}" for p, r in got), not leaked)


def write_root():
    try:
        with open("/var/tmp/payload.sh", "w") as f:      # /var/tmp is writable by anyone on a normal system
            f.write("echo hi\n")
        probe("leave something behind", "write /var/tmp/payload.sh (writable by anyone on a normal system)", "written", False)
    except OSError as e:
        probe("leave something behind", "write /var/tmp/payload.sh (writable by anyone on a normal system)",
              f"refused · {e.strerror or type(e).__name__}", True)


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


def metadata():
    """The cloud's metadata service: on a cloud VM, 169.254.169.254 hands out instance details and credentials to
    anything that can reach it. A sandbox must not."""
    try:
        socket.create_connection(("169.254.169.254", 80), timeout=3).close()
        probe("ask Vultr's metadata service", "connect to 169.254.169.254:80", "connected", False)
    except OSError as e:
        probe("ask Vultr's metadata service", "connect to 169.254.169.254:80", f"no route · {e.strerror or type(e).__name__}", True)


def host():
    """The server the room runs on, through Docker's own bridge (172.17.0.1), e.g. its ssh port."""
    try:
        socket.create_connection(("172.17.0.1", 22), timeout=3).close()
        probe("reach the server itself", "connect to the Docker host 172.17.0.1:22", "connected", False)
    except OSError as e:
        probe("reach the server itself", "connect to the Docker host 172.17.0.1:22", f"no route · {e.strerror or type(e).__name__}", True)


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
    attacks = (flood,) if mode == "flood" else (secrets, host_files, write_root, dns, raw_ip, metadata, host, root, memory)
    for attack in attacks:
        try:
            attack()
        except MemoryError:
            probe("eat the memory", "grab 1 GB, 64 MB at a time", "refused · MemoryError", True)
        except Exception as e:      # an attack that crashes is reported as such, never as "held"
            probe(attack.__name__, "", f"crashed · {type(e).__name__}: {e}"[:200], None)
    return {"fields": {}, "text": "break-in test finished", "notes": []}
