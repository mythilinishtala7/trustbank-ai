# Demo script (≈3 minutes)

Run the app first (see README). Open the Customer app at http://localhost:4300. All data is synthetic; no real money or PIN is used.

1. **Scenario A — routine payment.** Pay → tap "A · Routine rent payment" → Review payment. Risk is LOW, no questions, goes straight to the demo PIN. Enter any 4–6 digits and confirm; balance and history update.
2. **Scenario B — suspicious but not proven.** Pay → tap "B" → Review payment. A quick safety check appears with the evidence (new handle, burst of incoming transfers, links to flagged accounts) — note it does *not* claim prior complaints. Answer "A friend or family member" + "No" → REVIEW warning; the user must acknowledge before PIN.
3. **Scenario C — interception.** Start again with "C" (or B), answer "Telegram or WhatsApp" + "Yes". The PIN step is locked, specific indicators are listed, and a 2:00 simulated cooling-off timer starts. Cancel, or wait it out and see the server-side unlock.
4. **Investigator view.** Open Investigator view. Click *Nova Trade Desk* (WATCH): 0 complaints, but linked to flagged accounts. Open "AI decision log" → *Highlight on graph* to trace the payment and read each agent/engine step.

Tip: `HOLD_SECONDS=15` shortens the hold for quick rehearsals.
