"""Checks a scanner can't do: compare this invoice with what we already know about the vendor.

- bank details differ from the vendor's last paid invoice  -> the classic "we moved banks" fraud move
- the sender's domain differs from the vendor's usual domain (look-alike: .example vs .example.net)
Each flag blocks "Send to pay list" until the controller approves it.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# Vendor history: what was paid before. In the demo it's seeded; in a real shop it comes from the AP system.
HISTORY: Dict[str, dict] = {
    "granite peak refrigerants": {"last_invoice": "GPR-5520", "date": "09/30/2026", "total": 1284.00,
                                  "bank": "Canyon State Bank (EXAMPLE)", "routing": "000067890", "account_last4": "2208",
                                  "domain": "granitepeak-refrig.example"},
    "bonneville sheet metal supply": {"last_invoice": "BSM-23980", "date": "09/26/2026", "total": 512.40,
                                      "bank": "Mountain Ledger Bank (EXAMPLE)", "routing": "000012345", "account_last4": "4471",
                                      "domain": "bonneville-sheetmetal.example"},
}


def _key(vendor: Optional[str]) -> str:
    return re.sub(r"[^a-z ]", "", (vendor or "").lower()).strip()


def _domain(email: Optional[str]) -> str:
    m = re.search(r"@([\w.-]+)", email or "")
    return m.group(1).lower() if m else ""


def check(fields: dict, sender: Optional[str] = None) -> List[dict]:
    """Returns flags: {"code", "text", "blocks": True}. `sender` is the From address of the email that carried
    the file, when there is one (its domain is checked as well as the one printed on the invoice)."""
    out: List[dict] = []
    h = HISTORY.get(_key(fields.get("vendor")))
    if not h:
        return out
    bank = fields.get("bank") or {}
    r, a = (bank.get("routing") or "").strip(), (bank.get("account_last4") or "").strip()
    if (r and r != h["routing"]) or (a and a != h["account_last4"]):
        new_bank = (bank.get("name") or "a new bank").replace(" (EXAMPLE)", "")
        out.append({"code": "bank_changed", "blocks": True, "last_invoice": h["last_invoice"], "last_date": h["date"],
                    "was": f"{h['bank'].replace(' (EXAMPLE)', '')} ****{h['account_last4']}", "now": f"{new_bank} ****{a or '?'}",
                    "text": f"The bank account changed. The last invoice ({h['last_invoice']}, {h['date']}) was paid to "
                            f"{h['bank'].replace(' (EXAMPLE)', '')} ****{h['account_last4']}. This one asks for {new_bank} "
                            f"****{a or '?'}."})
    for who in filter(None, [sender, fields.get("sender_email")]):
        d = _domain(who)
        if d and d != h["domain"]:
            out.append({"code": "sender_domain", "blocks": True, "domain": d, "usual": h["domain"],
                        "text": f"It came from a new address, {d}; this vendor writes from {h['domain']}."})
            break
    return out


def hold_text(flags_: List[dict], vendor: str) -> str:
    """One paragraph for the clerk, flags in order, then what to do."""
    if not flags_:
        return ""
    return " ".join(f["text"] for f in flags_) + f" Call {vendor or 'the vendor'} on the number you already have before paying."
