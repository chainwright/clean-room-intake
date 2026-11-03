"""Control run for the break-in test: the SAME attack script, once, in an ordinary container with the walls taken
down (default runtime runc instead of gVisor, Docker's default network, writable root filesystem, Docker's default
capabilities; the image's own non-root user 65534, and the memory and process caps, are kept so the host stays safe). If the walls matter, attacks get through here
that are stopped in the room. Run on the VM, by hand, never from the web app.

    sudo .venv/bin/python deploy/breakin_control.py > docs/breakin_walls_off.json
"""
import json, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import sandbox, web  # noqa: E402

def walls_off(room, work, caps):
    return ["docker", "run", "--rm", "--name", room, "--runtime=runc", f"--memory={caps.memory_mb}m",
            f"--memory-swap={caps.memory_mb}m", f"--pids-limit={caps.pids}", "-v", f"{work}:/in:ro",
            sandbox.IMAGE, "python3", "-I", "/in/runner.py"]

code = open(os.path.join(os.path.dirname(sandbox.RUNNER), "breakin.py")).read()
rooms = [sandbox.run(w, code, cmd_for=walls_off).as_dict() for w in (b"walls", b"flood")]
out = {"setup": "runc (no gVisor), default network, writable root filesystem, default caps; kept: image user 65534, 512 MB, 128 pids",
       "probes": web.settle(rooms)}
json.dump(out, sys.stdout, indent=1)
