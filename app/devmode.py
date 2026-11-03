"""CLEANROOM_DEV=1: run the UI on a laptop with no Vultr key and no Docker.

NOT CONTAINMENT. The step runs as a plain local process (only the recording works, no walls) and the "model" is a
fixed script that reads fields with regexes. For UI work only; production always uses Docker + gVisor + Serverless
Inference.
"""
from __future__ import annotations

import json
import os
import re
import sys

STEP = '''
import os, zipfile, re
def extract(path):
    head = open(path, "rb").read(8)
    text = ""
    if head.startswith(b"%PDF"):
        import fitz
        text = "\\n".join(p.get_text() for p in fitz.open(path))
    elif head.startswith(b"PK"):
        z = zipfile.ZipFile(path)
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        text = re.sub(r"<w:p[ >]", "\\n<w:p ", xml)
        text = re.sub(r"<[^>]+>", "", text)
        # a renderer would follow external links; this step only reads them, the room has no network anyway
        rels = z.read("word/_rels/document.xml.rels").decode()
        for url in re.findall(r'Target="(https?://[^"]+)"', rels):
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=1)
            except Exception:
                pass
        if "KEY" in text:
            os.environ.get("VULTR_INFERENCE_KEY")   # what a naive step would do if it obeyed the hidden text
    else:
        text = "[scanned image: OCR runs in the room on the VM]"
    return {"text": text}
'''


def fake_llm(system: str, user: str) -> str:
    if system.startswith("You write"):
        return STEP
    t = user
    g = lambda p: (re.search(p, t, re.I | re.S) or [None, None])[1]
    tot = re.findall(r"(?<!Sub)(?<!sub)TOTAL(?: DUE)?\s*\$?([\d,]+\.\d\d)", t, re.I)
    total = tot[-1] if tot else None
    return json.dumps({
        "vendor": (g(r"<document>\s*\n?\s*([A-Z][^\n]+?)\n") or "").strip() or None,
        "invoice_no": g(r"INVOICE\s+([A-Z]{2,4}-\d+)"), "invoice_date": None,
        "due_date": g(r"Due:?\s*([\d/]{8,10})"), "total": float(total.replace(",", "")) if total else None,
        "currency": "USD", "pay_method": "ach" if re.search(r"routing", t, re.I) else "check",
        "bank": {"name": g(r"(\w+ \w+ Bank) \(EXAMPLE\)"), "routing": g(r"routing (\d{9})"), "account_last4": g(r"\*{4}(\d{4})")},
        "remit_to": g(r"(?:check to|Pay by check to)\s+([^\n<]+?)(?:\n|<|$)"),
        "sender_email": g(r"([\w.-]+@[\w.-]+\.example(?:\.net)?)"),
    })


def local_cmd(room, work, caps):
    return [sys.executable, "-I", os.path.join(work, "runner.py"), work]


ON = os.environ.get("CLEANROOM_DEV") == "1"
