# Demo script (about 4 minutes)

Open the live app at https://trustbank-pausepay.web.app (or `http://localhost:4200` locally; see `services/backend/API_TESTING.md`). All data is synthetic; no real money or PIN is used. The investigator access code is in Secret Manager (`trustbank-investigator-code`). Keep the console open in a second tab.

1. **Routine payment.** Enter as *Asha Menon*. Pay `rahul.verma@trustpay` 2,500. No questions, straight to the demo PIN (any 4 to 6 digits). Then pay `spice.garden@trustpay` 1,800: a high pass-through business with long dwell is not flagged.
2. **Unusual amount, no network evidence.** Pay `heritage.jewellers@trustpay` 40,000. Quick scam-check questions appear. Whatever you answer, the outcome is a review warning, never a hold, because the graph shows nothing wrong with the recipient.
3. **Fraudulent network.** Pay `nova.trade@trustpay` 25,000. Answer "A messaging app", "Yes" (promised a return), "Yes" (pressed to hurry). The payment is held and a 3-minute server-side timer starts; Cancel, or wait for expiry, then verify independently. With benign answers (invoice, "No", "No") the same payment ends in a review warning instead.
4. **Investigator console.** In `/investigation`, enter the access code and search the `txn_` reference. Walk through the live agent timeline, the graph path (Nova Trade, Quick Returns, Task Rewards, Swift Assist: money forwarded within minutes), the evidence with provenance badges, and the policy decision.
5. **Point to make.** The graph holds facts only. No complaint, flag or score is stored; the agents computed the risk from behavior (fast pass-through, near-zero retention, layering, fan-in). A graph connection is evidence to investigate, not proof.

Tip: set `TRUSTBANK_HOLD_SECONDS` low for quick rehearsals.
