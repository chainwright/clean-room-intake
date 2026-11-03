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


class Round13Bypasses(unittest.TestCase):
    """Round-13 judge: a known vendor's invoice that keeps the old details where the model looks, and puts the new
    ones under a label we didn't know, or writes the pay-to address only in the text."""
    G = {"vendor": "Granite Peak Refrigerants", "invoice_no": "GPR-5561", "total": 1236.0,
         "bank": {"routing": "000067890", "account_last4": "2208"}}
    BASE = "Granite Peak Refrigerants INVOICE GPR-5561 TOTAL $1,236.00 routing 000067890 "

    def codes(self, f):
        return [x["code"] for x in f]

    def test_new_account_under_an_unknown_label_holds(self):
        for tail in ("ref 2208. New beneficiary no. 0099887766", "account ending 2208. Updated deposit details: Konto 445566778899"):
            self.assertIn("bank_changed", self.codes(flags.check(self.G, text=self.BASE + tail)), tail)

    def test_account_spelled_in_words_holds(self):
        f = flags.check(self.G, text=self.BASE + "account ending 2208 (old). Please remit to acct number nine nine one three")
        self.assertIn("bank_unread", self.codes(f))

    def test_same_details_still_pay(self):
        self.assertEqual(flags.check(self.G, text=self.BASE + "account ****2208"), [])

    def test_check_address_only_in_the_text_holds(self):
        bc = {"vendor": "Bonneville Sheet Metal Supply", "invoice_no": "BSM-24117", "total": 736.81, "pay_method": "check",
              "remit_to": "2140 S 300 W, Salt Lake City, UT"}         # the model reports the address on file
        f = flags.check(bc, text="Bonneville Sheet Metal Supply BSM-24117 $736.81 Mail checks to PO Box 9911, Henderson NV")
        self.assertEqual(self.codes(f), ["remit_changed"])
        ok = flags.check(bc, text="Bonneville Sheet Metal Supply BSM-24117 $736.81 Remit to: 2140 S 300 W, Salt Lake City, UT 84115")
        self.assertEqual(ok, [])
