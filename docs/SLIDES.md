# Slides (PDF for lablab), outline v1 — 8 slides, direction A visuals

1. **$3.05 billion.** US businesses reported $3.05B lost to business email compromise in 2025 (FBI IC3, 2025 Internet
   Crime Report, p. 8). Under it: "A changed bank account on a normal-looking invoice is how a lot of it starts."
   ⚠ the second sentence needs its own source or goes (PLAN "Numbers").
2. **Marisol opens 30–80 files a day from strangers.** Two bad options today: open and hope, or retype from a preview.
3. **Clean Room Intake.** "Open files from strangers without opening your business to them." Screenshot: desk | glass |
   booth, the trap file's attempts on the glass, the clean slip on the desk.
4. **How it works (Track 1, Pattern A).** Model writes the extraction step → runs in a throwaway gVisor room on Vultr →
   text out through the drawer → error? back to the model (≤2) → fields read as untrusted data → room destroyed.
5. **The walls, with numbers.** Table from README "Containment", filled from `docs/containment_check.txt` on the VM.
6. **The containment moment.** The test file: tried collect.attacker.example → no network; tried VULTR_INFERENCE_KEY →
   nothing there; hidden instruction → ignored; fields still came back; room destroyed at T+0.7 s.
7. **The check a scanner can't do.** Granite Peak: bank details differ from GPR-5520, look-alike sender domain →
   HOLD until the controller approves.
8. **Business value and what's next.** Who pays (AP teams of 10–500 people; per-seat), what it replaces (manual
   retyping, "open and hope"), next: email-inbox connector, vendor-history sync from QuickBooks/NetSuite,
   per-tenant VM isolation. Vultr services list. Repo + demo URL.
