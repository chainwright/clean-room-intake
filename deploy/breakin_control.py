"""Control runs for the break-in test: the SAME attack script (sha256 recorded) in three set-ups, on the VM, by hand.

  room        the real room: gVisor (runsc), no network, read-only, no capabilities, non-root, caps
  plain       an ordinary container WITHOUT gVisor (runc) but with the same network/disk/user/capability walls
  walls_down  runc, Docker's default network, writable root filesystem, default capabilities
Kept in all three: the image's non-root user 65534, 512 MB, 128 processes (so the host stays safe).
Shows which wall stops what, and what gVisor adds on top of the ordinary container walls.

    sudo .venv/bin/python deploy/breakin_control.py > docs/breakin_controls.json
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import sandbox, web  # noqa: E402


def plain(room, work, caps):
    return [x.replace("--runtime=runsc", "--runtime=runc") for x in sandbox.docker_cmd(room, work, caps)]


def walls_down(room, work, caps):
    return ["docker", "run", "--rm", "--name", room, "--runtime=runc", f"--memory={caps.memory_mb}m",
            f"--memory-swap={caps.memory_mb}m", f"--pids-limit={caps.pids}", "-v", f"{work}:/in:ro",
            sandbox.IMAGE, "python3", "-I", "/in/runner.py"]


path = os.path.join(os.path.dirname(sandbox.RUNNER), "breakin.py")
code = open(path).read()
out = {"script_sha256": hashlib.sha256(code.encode()).hexdigest(), "setups": {}}
for name, cmd in (("room", sandbox.docker_cmd), ("plain", plain), ("walls_down", walls_down)):
    rooms = [sandbox.run(w, code, cmd_for=cmd).as_dict() for w in (b"walls", b"flood")]
    out["setups"][name] = [{k: p.get(k) for k in ("attack", "how", "outcome", "held")} for p in web.settle(rooms)]
json.dump(out, sys.stdout, indent=1)
