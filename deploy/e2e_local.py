"""End to end with real walls: every sample through Docker + gVisor (runsc) and a real OpenAI-compatible model.

    LLM_BASE_URL=... LLM_KEY=... LLM_MODEL=... python3 deploy/e2e_local.py [out.json]

On the Vultr VM the model is Serverless Inference; on a laptop any OpenAI-compatible endpoint stands in.
Prints one line per file: state, fields, attempts recorded, room lifetime.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openai import OpenAI  # noqa: E402

from app import agent, flags, sandbox  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_KEY"])


def llm(system, user):
    r = client.chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0,
                                       messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content or ""


out = []
inbox = os.path.join(ROOT, "demo", "inbox")
for name in sorted(os.listdir(inbox)):
    if name.startswith("granite") and name.endswith(".docx"):
        continue                      # the .eml carries it
    data = open(os.path.join(inbox, name), "rb").read()
    sender = ""
    if name.endswith(".eml"):
        import email
        from email import policy
        m = email.message_from_bytes(data, policy=policy.default)
        sender = str(m.get("From", ""))
        part = next(m.iter_attachments())
        name, data = part.get_filename(), part.get_content()
    states = []
    it = agent.run(name, data, llm=llm, on_state=lambda s: states.append(s))
    f = flags.check(it.fields, sender=sender or None, text=it.text, notes=it.flags,
                    attempts=[a for t in it.tries for a in t["receipt"]["attempts"]])   # the same checks as the app
    rec = it.tries[-1]["receipt"] if it.tries else {}
    row = {"file": name, "state": states[-2] if len(states) > 1 else it.state, "fields": it.fields, "flags": [x["code"] for x in f],
           "notes": it.flags, "tries": len(it.tries), "error": it.error or rec.get("error", ""),
           "attempts": [a["what"] + " " + a["detail"][:80] for t in it.tries for a in t["receipt"]["attempts"]],
           "killed_by": rec.get("killed_by"), "lived_s": round(rec.get("destroyed", 0) - rec.get("started", 0), 2)}
    out.append(row)
    print(json.dumps({k: row[k] for k in ("file", "state", "tries", "flags", "attempts", "lived_s", "error")}))
    print("   fields:", json.dumps({k: row["fields"].get(k) for k in ("vendor", "invoice_no", "total", "due_date")}))
if len(sys.argv) > 1:
    json.dump(out, open(sys.argv[1], "w"), indent=1)
