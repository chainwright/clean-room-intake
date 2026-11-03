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


TOOLS = {"tesseract"}
SENSITIVE = ("/etc/", "/proc/", "/sys/", "/root", "/home/", "/run/", "/var/run/")


def emit(**kw):
    kw["t"] = round(time.monotonic() - T0, 4)
    sys.__stdout__.write(json.dumps(kw, default=str) + "\n")
    sys.__stdout__.flush()


def hook(event, args):
    if event not in WATCH:
        return
    if event == "subprocess.Popen" and os.path.basename(str(args[0])) in TOOLS:
        return                                    # the OCR engine the step is allowed to call
    if event == "open":
        if not isinstance(args[0], (str, bytes)):  # an already-open file descriptor
            return
        path, mode = str(args[0]), str(args[1] or "r") if len(args) > 1 else "r"
        if path == "/tmp":
            return
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


CHROME_FLAGS = ["--headless=new", "--disable-gpu", "--no-sandbox", "--no-zygote", "--disable-crash-reporter",
                "--disable-breakpad", "--disable-dev-shm-usage",   # gVisor is the sandbox; check --single-process on the VM if memory is tight
                "--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run",
                "--disable-default-apps", "--window-size=1000,1300"]


def render_preview(path):
    """HTML files: render the page the way a mail client or preview pane would, in the room, with Chromium's own
    net log. Every URL the page itself tried becomes an attempt (the room has no network, so each one fails)."""
    import subprocess
    sys.path.insert(0, IN)
    import netlog
    chrome = os.environ.get("CLEANROOM_CHROME", "chromium")
    log, shot = "/tmp/net.json", "/tmp/preview.png"
    html = path + ".html" if not path.endswith(".html") else path
    if html != path:
        html = "/tmp/page.html"
        with open(path, "rb") as src, open(html, "wb") as dst:
            dst.write(src.read())
    try:
        subprocess.run([chrome, *CHROME_FLAGS, "--user-data-dir=/tmp/chrome", f"--log-net-log={log}",
                        f"--screenshot={shot}", "file://" + html], capture_output=True, timeout=20,
                       env={**os.environ, "HOME": "/tmp"})     # read-only root: the browser's profile lives in /tmp
    except Exception as e:
        emit(ev="note", note=f"preview renderer didn't run: {type(e).__name__}")
        return
    try:
        for a in netlog.attempts(log):
            emit(ev="attempt", what="browser", detail=f"{a['url']} ({a['error']})")
    except Exception as e:
        emit(ev="note", note=f"couldn't read the renderer's log: {type(e).__name__}")


def main():
    if os.path.exists(IN + "/render_html"):     # the orchestrator asks for a preview render (HTML invoices)
        render_preview(IN + "/file")            # before the audit hook: the renderer's own subprocess isn't the step
    # the step sees only what a program needs to run; the base image's own variables (e.g. Python's public GPG_KEY
    # fingerprint) are dropped too, so "secrets inside: 0" holds for the step, not just for our flags
    for k in list(os.environ):
        if k not in ("PATH", "HOME", "LANG", "LC_ALL", "CLEANROOM_CHROME"):
            del os.environ[k]
    # measured, not assumed: what the step can see, and how many of those names look like secrets
    emit(ev="env", names=sorted(os.environ), secretlike=sum(1 for k in os.environ if SECRETY.search(k)))
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
