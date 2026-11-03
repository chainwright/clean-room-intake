"""Runs inside the throwaway sandbox. Never sees an API key.

Input:  /in/file   (the stranger's file, read-only)
        /in/step.py (the extraction step the model wrote)
Output: one JSON object per line on stdout:
        {"ev": "attempt", "what": "socket.connect", "detail": "...", "t": 0.012}   every risky thing the file or step tried
        {"ev": "result", "fields": {...}, "text": "..."}                         what the step returned
        {"ev": "error", "error": "..."}                                          the step raised

The audit hook only *records*: the walls are the container's (no network, read-only root, no secrets, caps).
The receipt shows both: what was tried (from here) and what stopped it (from the orchestrator).
"""
import json
import os
import re
import sys
import time

T0 = time.monotonic()
IN = sys.argv[1] if len(sys.argv) > 1 else "/in"     # tests run the runner outside a container
WATCH = {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "urllib.Request", "subprocess.Popen",
         "os.system", "os.exec", "os.posix_spawn", "os.fork", "ctypes.dlopen", "open"}


SENSITIVE = ("/etc/", "/proc/", "/sys/", "/root", "/home/", "/run/", "/var/run/")


def emit(**kw):
    kw["t"] = round(time.monotonic() - T0, 4)
    sys.__stdout__.write(json.dumps(kw, default=str) + "\n")
    sys.__stdout__.flush()


def hook(event, args):
    if event not in WATCH:
        return
    if event == "open":
        path, mode = str(args[0]), str(args[1] or "r") if len(args) > 1 else "r"
        writing = any(c in mode for c in "wax+")
        # reading libraries and the input is normal; writing anywhere, or reading where secrets live, is an attempt
        if path.startswith("/tmp/") or (not writing and not path.startswith(SENSITIVE)):   # /tmp is the scratch tmpfs
            return
        emit(ev="attempt", what="open", detail=f"{path} ({'write' if writing else 'read'})")
        return
    emit(ev="attempt", what=event, detail=repr(args)[:200])


SECRETY = re.compile(r"(?i)key|token|secret|passw|auth|cred|cookie|session|aws_|gcp_|azure_|vultr")


class WatchedEnv(dict):
    """os.environ stand-in. Libraries read ordinary settings all the time (PyMuPDF reads several); only a read of a
    secret-looking name is an attempt worth a line. The sandbox has no such variables anyway."""

    def _seen(self, k):
        if SECRETY.search(str(k)):
            emit(ev="attempt", what="getenv", detail=k)

    def __getitem__(self, k):
        self._seen(k)
        return super().__getitem__(k)

    def get(self, k, default=None):
        self._seen(k)
        return super().get(k, default)


def main():
    os.environ = WatchedEnv(os.environ)          # noqa: B003 (deliberate)
    sys.addaudithook(hook)
    ns = {"__name__": "step", "FILE": IN + "/file"}
    try:
        with open(IN + "/step.py") as f:
            code = f.read()
        exec(compile(code, "step.py", "exec"), ns)  # the model-written step defines extract(path) -> dict
        out = ns["extract"](IN + "/file")
        emit(ev="result", fields=out.get("fields", {}), text=str(out.get("text", ""))[:20000],
             notes=out.get("notes", []))
    except BaseException as e:   # MemoryError, RecursionError, anything: report and exit cleanly
        emit(ev="error", error=f"{type(e).__name__}: {e}"[:500])


if __name__ == "__main__":
    main()
