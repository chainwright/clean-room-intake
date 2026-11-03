# Clean Room Intake

**Open files from strangers without opening your business to them.**

Scanners tell you a file looks clean. Clean Room Intake opens it where it can't hurt you, and tells you what it tried.

Every invoice is opened only inside a throwaway sandbox on Vultr: no network, no secrets, capped memory and time,
destroyed afterwards. The clerk gets clean fields and a plain-text copy. The controller gets a receipt of what the
file tried to do and what stopped it, plus the check that pays for itself: **the bank details on this invoice differ
from the vendor's last one.**

> Demo: https://149-248-46-73.sslip.io (Vultr Cloud Compute, Seattle; Caddy + Let's Encrypt in front) · Video: ⟨link⟩ · Track 1, Blast Radius Zero

## Use case
Marisol Reyes does accounts payable at a 40-person HVAC company in Salt Lake City. Every day she opens 30 to 80
invoices from people she has never met: PDFs, phone scans, Word files, emails with attachments. Today she has two bad
options: open everything on her own machine and hope, or retype from a preview and lose an hour.

US businesses reported **$3.05 billion** lost to business email compromise in 2025 (FBI IC3, 2025 Internet Crime
Report, p. 8). A changed bank account on an otherwise normal invoice is one of the oldest moves in that playbook.

Clean Room Intake removes the choice:
1. Marisol drops a file, or forwards the email.
2. A fresh sandbox opens it on the other side of the glass; she watches it happen.
3. She gets the vendor, invoice number, amount, due date and bank details as plain text, each with the page it came from.
4. The sandbox is destroyed. The receipt stays (in the app's memory for the demo; a restart clears it).
5. **Send to pay list** is held until the controller approves whenever the bank details changed, the email came from
   a look-alike domain, the pay-to address changed, the file tried to reach anything while open, the file carries hidden
   instructions, or the vendor has never been paid before (any pay method, checks included). Approval covers exactly the
   holds the controller saw (a new hold needs a new approval), and a hold about who gets the money can't be approved
   without a written call note (who called, on which number from your own records), which stays on the receipt. The hold fails closed
   and doesn't trust the model: every field the model reported is checked against the text that came out of the room
   (shown as ✓ / ✕ on the slip), and the bank check also runs on that text directly, so a document that talks the model
   into reporting the old account still holds: any long number after a pay word (beneficiary, deposit, Konto, wire…)
   that isn't on file, an account written out in words, or a pay-to address in the text that isn't the one on file.

## Vultr services
| Service | What it does here |
|---|---|
| **Cloud Compute VM** (Ubuntu 24.04) | The web app and the orchestrator: queue, sandbox lifecycle, receipts, flags. The control layer. |
| **Docker + gVisor (`runsc`) on that VM** | One throwaway container per file, behind a user-space kernel. |
| **Serverless Inference** (OpenAI-compatible, `api.vultrinference.com/v1`) | Every model call: writing the extraction step, fixing it after an error, reading the fields. Model: `mimo-v2.6-flash`, picked from the live `/v1/models` list by measuring our real prompt on the VM: it writes the extraction step in ~3 s (≈900 tokens) where the reasoning-heavy models took 24–80 s (7k–33k tokens); reading the fields takes ~1 s. |

## Architecture
```
 browser ──► FastAPI on the Vultr VM (orchestrator, holds the inference key)
                │
                │ 1. ask Serverless Inference: "write extract(path) for this kind of file"
                │ 2. docker run --runtime=runsc --network=none --read-only ... (file + step, read-only)
                │        └─ runner.py: runs the step, records every attempt (socket, getenv, exec, open)
                │ 3. text comes back out; error? → back to the model, max 2 retries
                │ 4. ask Serverless Inference for the fields, text marked as UNTRUSTED data
                │ 5. flags: vendor history (bank details, sender domain)
                └─ 6. container removed; receipt stored
```
The model never opens the file: it reads only the text that came out of the sandbox, marked as untrusted data. One more
thing crosses from the room to the step-writing model: when a step fails, its error message (cut to 200 characters) goes
back so the model can fix the step. A file could shape that message; at most it shapes the next step, which runs behind
the same walls. The sandbox never sees the key.

## Containment (the walls, with numbers)
End to end on the VM with the real model (`docs/e2e_vultr.json`): all six sample files run, five read and one (the damaged copy) held as unreadable; the bank-change invoice raised both
flags, every first-time vendor is held, and the file that tried to call out is held; the HTML test file's two requests (to `example.com` and `1.1.1.1`) were stopped inside the room while both hosts answered from outside; rooms lived from under 1 s to about 8 s and were removed.

| Wall | Setting | Checked on the Vultr VM (`deploy/containment_check.sh` → `docs/containment_check_vultr.txt`; Seattle, vc2-2c-4gb, x86_64, runsc release-20261102.0, 03.11) |
|---|---|---|
| Kernel | gVisor `runsc` between the file and the host | `dmesg`: "Starting gVisor..." |
| Network | `--network=none` | connect to example.com: name resolution fails |
| Secrets | no environment passed in; the key stays in `/etc/cleanroom.env` for the orchestrator only; the runner drops the base image's variables before the step runs | measured in every room and printed on its receipt: the step sees only `HOME LANG PATH`, 0 secret-looking names |
| Filesystem | `--read-only`, 64 MB tmpfs, input mounted read-only | write to `/`: refused |
| Memory | 512 MB, no swap | 1 GB allocation: killed (exit 137) |
| Processes | 128 pids | containment check: 500 `sleep` processes, stopped at 50 (`ENOMEM`). Break-in flood (500 forks, `deploy/flood_cap_control.sh` → `docs/flood_cap_control.txt`): with the 128 cap, gVisor ends the room after 50 forks (exit 2); with the cap raised to 1000, the 512 MB memory cap kills it after 71 (exit 137). Two walls behind each other |
| Time | 30 s, then `docker rm -f` | containers left after all runs: 0 |
| Privileges | `--cap-drop=ALL`, `no-new-privileges`, user 65534 | `CapEff 0000000000000000`, uid 65534 |

The receipt shows both sides: what the file tried (from inside), and which wall stopped it (from outside).
The "tried" lines are recorded inside the room by the same process that runs the model's code, so they are evidence,
not enforcement: code in the room could hide its own attempts, but it can't get through the walls, which Docker and
gVisor enforce from outside. The room's output is read with a 2 MB cap, so it can't flood the orchestrator either.

## Run locally
```
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn openai python-multipart pymupdf python-docx pillow
.venv/bin/python demo/make_files.py           # the sample inbox
.venv/bin/python -m unittest discover tests   # logic tests (the walls are tested on the VM)
docker build -t cleanroom-runner:1 sandbox/   # needs Docker + gVisor for real containment
VULTR_INFERENCE_KEY=... CLEANROOM_MODEL=... .venv/bin/uvicorn app.web:app
```

## What's simulated
- The companies, people, invoices and bank numbers are fictional (RFC 2606 `.example` domains, `555-01xx` phones,
  bank numbers starting `0000`).
- **`jordan_river_JRP-7781_TESTFILE.docx` is our own harmless test file.** It carries hidden instruction-like text
  (white on white) aimed at the model; the receipt quotes it word for word.
- **`wasatch_valve_WVS-3310_TESTFILE.html` is our own harmless test file.** Rendered in the room the way a mail client
  would, it tries to load an image from `example.com` and to send its title to `1.1.1.1` (both real, both answer from
  anywhere with a network). Inside the room Chromium's own net log records `ERR_NAME_NOT_RESOLVED` and
  `ERR_ADDRESS_UNREACHABLE`; as a control, the server then checks the same hosts from outside the room (bare host, nothing
  from the file sent) and the receipt shows they answer.
- **The break-in test (`sandbox/breakin.py`) is our own attack script**, run in two fresh rooms with exactly the walls a
  file gets: read keys from the environment, open password/key files, write to `/`, look up a name, connect to an IP,
  reach Vultr's metadata service (169.254.169.254), reach the server itself through Docker's bridge (172.17.0.1:22), read which kernel it talks to,
  `setuid(0)`, grab 1 GB, fork 500 processes. The two attacks that end a room are judged from outside (exit code, and
  the forks the room's own audit hook recorded).
  **Control runs** (`deploy/breakin_control.py` → `docs/breakin_controls.json`, script sha256 recorded): the same 11
  attacks in three set-ups, all keeping the image's non-root user and the 512 MB / 128-process caps:

  | set-up | got through |
  |---|---|
  | the room: gVisor, no network, read-only, no capabilities | 0 of 11 |
  | an ordinary container (runc) with the same network/disk/capability walls | 1 of 11: it sees the server's own kernel |
  | walls down: runc, Docker's default network, writable root filesystem | 6 of 11: disk, name lookup, IP, Vultr metadata, the host, the kernel |

  Said plainly: the ten "doing" attacks are stopped by the container walls; what gVisor adds, measurably, is that code
  in the room never makes system calls into the server's kernel directly (gVisor's own user-space kernel answers them,
  and the room reports gVisor's kernel, not the server's), which is what a kernel exploit needs.
  We don't ship kernel exploits, so that second wall is shown, not stress-tested.
- The vendor history (last invoice and bank details per vendor) is seeded; in a real shop it comes from the AP system.
- **What runs outside the room, said plainly:** a forwarded `.eml` is unpacked on the server by Python's standard
  `email` parser to get the sender and the attachment (the attachment itself only ever opens in the room); the app user
  is in the `docker` group, which on Docker is root-equivalent on the VM (a production install would use rootless
  Docker or a separate launcher); receipts live in memory for the demo and are gone after a restart.
- **The demo has no login.** Each browser gets its own desk (a random visitor id in a cookie): it sees, approves and
  pays only its own files; another visitor's file answers 404. Approving is a click, not a signed-in controller; a real
  deployment sits behind the company's sign-in, with approvals tied to the controller's account.
- Everything else is live: the sandbox, its caps, its destruction, and every model call.

## Licence
MIT
