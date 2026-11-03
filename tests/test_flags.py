import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import flags  # noqa: E402


class Flags(unittest.TestCase):
    def test_granite_peak_new_bank_and_lookalike_domain(self):
        f = {"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0, "bank": {"name": "Summit Ridge Bank (EXAMPLE)", "routing": "000098765", "account_last4": "9013"},
             "sender_email": "ar@granitepeak-refrig.example"}
        out = flags.check(f, sender="Kelsey <ar@granitepeak-refrig.example.net>")
        codes = [x["code"] for x in out]
        self.assertEqual(codes, ["bank_changed", "sender_domain"])
        self.assertIn("GPR-5520", out[0]["text"])
        self.assertIn("Canyon State Bank ****2208", out[0]["text"])
        self.assertIn("Summit Ridge Bank ****9013", out[0]["text"])
        self.assertTrue(flags.hold_text(out, "Granite Peak").endswith("before paying."))
        self.assertIn("granitepeak-refrig.example.net", out[1]["text"])
        self.assertTrue(all(x["blocks"] for x in out))

    def test_same_bank_same_domain_no_flags(self):
        f = {"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24117", "total": 736.81, "bank": {"routing": "000012345", "account_last4": "4471"},
             "sender_email": "billing@bonneville-sheetmetal.example"}
        self.assertEqual(flags.check(f), [])

    def test_unknown_vendor_no_guessing(self):
        self.assertEqual(flags.check({"vendor": "Red Butte Electrical Contractors", "invoice_no": "RB-0932", "total": 450.9}), [])

    def test_missing_bank_on_invoice_is_not_a_change(self):
        self.assertEqual(flags.check({"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0, "bank": {}}), [])


if __name__ == "__main__":
    unittest.main()
