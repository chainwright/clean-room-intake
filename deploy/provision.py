"""Create the Vultr side once the hackathon credit is on the account. Idempotent: finds what already exists by label.

    VULTR_API_KEY=... python3 deploy/provision.py plan       # show regions/plans/os it would use, change nothing
    VULTR_API_KEY=... python3 deploy/provision.py up         # ssh key + VM (cloud-init) + Serverless Inference
    VULTR_API_KEY=... python3 deploy/provision.py status     # IP, state, inference subscription

The account API key never goes to the VM. The inference key is copied to the VM's /etc/cleanroom.env by setup over ssh.
Docs: https://www.vultr.com/api/ (v2), Serverless Inference: https://docs.vultr.com/products/serverless/inference/
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import urllib.request

API = "https://api.vultr.com/v2"
LABEL = "clean-room-intake"
HERE = pathlib.Path(__file__).resolve().parent
SSH_KEY = pathlib.Path.home() / ".ssh" / "cleanroom_vultr_ed25519"
PREFERRED_REGIONS = ["sea", "lax", "sjc", "dfw", "ord"]     # west first: closest to the SLC on-site
PLAN_MIN = {"vcpu_count": 2, "ram": 4096}


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": "Bearer " + os.environ["VULTR_API_KEY"],
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def pick():
    regions = {r["id"] for r in call("GET", "/regions?per_page=500")["regions"]}
    region = next((r for r in PREFERRED_REGIONS if r in regions), sorted(regions)[0])
    plans = [p for p in call("GET", "/plans?type=vc2&per_page=500")["plans"]
             if p["vcpu_count"] >= PLAN_MIN["vcpu_count"] and p["ram"] >= PLAN_MIN["ram"] and region in p["locations"]]
    plan = min(plans, key=lambda p: p["monthly_cost"])
    os_id = next(o["id"] for o in call("GET", "/os?per_page=500")["os"] if o["name"].startswith("Ubuntu 24.04") and "x64" in o["name"])
    return region, plan, os_id


def ensure_ssh_key() -> str:
    if not SSH_KEY.exists():
        os.system(f'ssh-keygen -q -t ed25519 -N "" -C {LABEL} -f "{SSH_KEY}"')
    pub = (SSH_KEY.with_suffix(".pub")).read_text().strip()
    for k in call("GET", "/ssh-keys")["ssh_keys"]:
        if k["name"] == LABEL:
            return k["id"]
    return call("POST", "/ssh-keys", {"name": LABEL, "ssh_key": pub})["ssh_key"]["id"]


def find_instance():
    return next((i for i in call("GET", "/instances?per_page=500")["instances"] if i["label"] == LABEL), None)


def find_inference():
    try:
        subs = call("GET", "/inference")
    except Exception as e:      # the product may not be on the account yet
        return {"error": str(e)}
    return next((s for s in subs.get("subscriptions", []) if s.get("label") == LABEL), None)


def main(cmd: str):
    if cmd == "plan":
        region, plan, os_id = pick()
        print(json.dumps({"region": region, "plan": plan["id"], "monthly_cost": plan["monthly_cost"], "os_id": os_id}, indent=1))
    elif cmd == "up":
        region, plan, os_id = pick()
        inst = find_instance()
        if not inst:
            inst = call("POST", "/instances", {
                "region": region, "plan": plan["id"], "os_id": os_id, "label": LABEL, "hostname": LABEL,
                "sshkey_id": [ensure_ssh_key()], "backups": "disabled", "enable_ipv6": False,
                "user_data": base64.b64encode((HERE / "cloud-init.yaml").read_bytes()).decode()})["instance"]
        inf = find_inference()
        if not inf or "error" in (inf or {}):
            inf = call("POST", "/inference", {"label": LABEL}).get("subscription")
        print(json.dumps({"instance": {k: inst.get(k) for k in ("id", "main_ip", "status", "region", "plan")},
                          "inference": {k: (inf or {}).get(k) for k in ("id", "label", "date_created")}}, indent=1))
    elif cmd == "status":
        inst, inf = find_instance(), find_inference()
        print(json.dumps({"instance": inst and {k: inst.get(k) for k in ("id", "main_ip", "status", "power_status", "server_status")},
                          "inference": inf and {k: inf.get(k) for k in ("id", "label")}}, indent=1))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
