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

    def test_unknown_vendor_is_held_whatever_the_pay_method(self):
        # fails closed: a check to a vendor we have never paid is the same risk as a new bank account
        for pm in ("check", None):
            f = flags.check({"vendor": "Red Butte Electrical Contractors", "invoice_no": "RB-0932", "total": 9800.0, "pay_method": pm})
            self.assertEqual([x["code"] for x in f], ["new_vendor"])

    def test_known_vendor_new_remit_address_holds(self):
        f = flags.check({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24200", "total": 736.81,
                         "pay_method": "check", "remit_to": "PO Box 7781, Ogden, UT"})
        self.assertEqual([x["code"] for x in f], ["remit_changed"])
        same = flags.check({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24200", "total": 736.81,
                            "pay_method": "check", "remit_to": "2140 South 300 West, SLC, Utah"})
        self.assertEqual(same, [])                                   # the same address written differently is not a change
        unread = flags.check({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24200", "total": 736.81,
                              "pay_method": "check"})
        self.assertEqual([x["code"] for x in unread], ["remit_changed"])   # a check with no readable address holds

    def test_vendor_name_must_be_in_the_text(self):
        f = flags.check({"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "X-1", "total": 5.0},
                        text="Bonneville Sheet Metal Supplies Ltd X-1 $5.00")
        self.assertIn("not_in_text", [x["code"] for x in f])

    def test_missing_bank_on_invoice_is_not_a_change(self):
        self.assertEqual(flags.check({"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0, "bank": {}}), [])


if __name__ == "__main__":
    unittest.main()
