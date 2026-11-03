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


ROUTING = re.compile(r"(?<!\d)(\d{9})(?!\d)")
# account numbers as invoices print them: "****9013", "account ending 9013", "Acct #: 000123459013", "account 9013"
ACCOUNT = re.compile(r"(?i)(?:\*{2,}\s*|x{2,}\s*|ending(?:\s+in)?\s+|acc(?:oun)?t\.?\s*(?:no\.?|number|#)?\s*:?\s*)(\d{4,17})\b")
BANKISH = re.compile(r"(?i)\b(routing|aba|account\s*(no|number|#)?|acct|iban|swift|bic|wire|ach|bank)\b")


def _digits(text: str) -> str:
    """Digits written with spaces, dots or dashes between them ("0000 98765", "000-098-765") read as one number."""
    return re.sub(r"(?<=\d)[\s.\-‐–]+(?=\d)", "", text or "")


def _money(v) -> List[str]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return []
    return [f"{x:,.2f}", f"{x:.2f}"]


def verify(fields: dict, text: str) -> List[dict]:
    """The model's answer, checked against the text that came out of the room, without the model: every field it
    reported has to be in the file's own text. A field the model invented (or was talked into) shows up as not found."""
    t = text or ""
    low = t.lower()
    bank = fields.get("bank") or {}
    rows = []
    for name, value, forms in (("invoice", fields.get("invoice_no"), [str(fields.get("invoice_no") or "").lower()]),
                               ("amount", fields.get("total"), _money(fields.get("total"))),
                               ("routing", bank.get("routing"), [str(bank.get("routing") or "")]),
                               ("account", bank.get("account_last4"), [str(bank.get("account_last4") or "")])):
        if value in (None, ""):
            continue
        hay = low if name == "invoice" else _digits(t) if name in ("routing", "account") else t
        found = any(f and f in hay for f in forms)
        rows.append({"field": name, "value": value, "found": found})
    return rows


def check(fields: dict, sender: Optional[str] = None, text: str = "", notes: Optional[List[str]] = None) -> List[dict]:
    """Returns flags: {"code", "text", "blocks": True}. Fails closed: a hold unless the payment details are known good.
    `sender` is the From address of the email that carried the file. `text` is what came out of the room: the bank
    check runs on it directly as well, so a document that talks the model into reporting the old account still holds."""
    out: List[dict] = []
    missing = [k for k, v in (("amount", (fields or {}).get("total")), ("invoice number", (fields or {}).get("invoice_no"))) if v in (None, "")]
    if missing and (fields or text):              # read something, but not what a payment needs: hold, don't call it ready
        out.append({"code": "incomplete", "blocks": True,
                    "text": f"Couldn't read the {' or the '.join(missing)} from this file. Ask the vendor for a clean copy before paying."})
    for row in (verify(fields, text) if text else []):      # no text out of the room = nothing was read to verify
        if not row["found"]:
            out.append({"code": "not_in_text", "blocks": True, "field": row["field"], "value": row["value"],
                        "text": f"The model reported {row['field']} {row['value']}, but it isn't in the file's text."})
    if any("instruction" in n.lower() for n in (notes or [])):
        out.append({"code": "hidden_instructions", "blocks": True,
                    "text": "The file carries hidden instructions aimed at software. A person should look at it before it is paid."})
    h = HISTORY.get(_key(fields.get("vendor")))
    bank = fields.get("bank") or {}
    if not h:
        if (fields.get("pay_method") == "ach") or bank.get("routing") or bank.get("account_last4") or ROUTING.search(text or ""):
            out.append({"code": "new_vendor", "blocks": True,
                        "text": "First invoice from this vendor with bank details: confirm them by phone before the first payment."})
        return out
    r, a = re.sub(r"\D", "", bank.get("routing") or ""), re.sub(r"\D", "", bank.get("account_last4") or "")
    in_text = set(ROUTING.findall(_digits(text)))
    accts = {m[-4:] for m in ACCOUNT.findall(_digits(text)) if m[-4:] != h["routing"][-4:] or len(m) != 9}
    changed = (r and r != h["routing"]) or (a and a != h["account_last4"]) or bool(in_text - {h["routing"]}) \
        or bool(accts - {h["account_last4"]})          # an account in the file's own text that isn't the one on file
    if not changed and r and not a:
        out.append({"code": "bank_unread", "blocks": True,
                    "text": "The model reported a routing number but no account. Check the account against the vendor's "
                            "record before paying."})
    if not changed and not (r or a) and text and BANKISH.search(text) and h["routing"] not in in_text:
        # the file talks about bank details but the model reported none, and the known account isn't in the text:
        # don't assume nothing changed
        out.append({"code": "bank_unread", "blocks": True,
                    "text": "The invoice mentions bank details, but they couldn't be matched to the account on file. "
                            "Check them against the vendor's record before paying."})
    if changed:
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
