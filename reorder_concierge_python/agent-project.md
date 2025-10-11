📦 Automated Re-Order Concierge (LangGraph + HITL)

🎯 Problem

Small online retailers often lose sales because stockouts aren’t noticed until it’s too late.
Cancellations hurt both revenue and customer trust.


---

🤖 Solution

We design an Automated Re-Order Concierge:

A background workflow that monitors inventory every hour.

If stock drops below a threshold, it requests human approval before auto-ordering.

Uses LangGraph to orchestrate logic as a state machine.

Integrates HITL (Human-in-the-loop) so the owner stays in control with one-click confirm/reject links.



---

🛠️ Workflow (Conceptual)

1. Scheduled Trigger → Every hour.


2. Inventory Check → Read Google Sheets (on_hand_qty vs. reorder_threshold).


3. Candidate Selection → Only process items last checked >24h ago.


4. Approval Step (HITL) →

Owner (your email address)receives an email with item details + “Confirm” / “Reject” buttons.


5. Confirm Path →

Update “last_checked” in the sheet.

Draft with an llm a Purchase Order (PO) with SKU, qty, address and privider name.

Send email to supplier (cc: owner).

Log PO in sheet.



6. Reject Path →

Update “last_checked”.

Write comment = “Rejected by owner”.



7. Error Handling → If email fails, alert owner immediately.




---


🎥 Video Demo Checklist

✅ Start by showing Google Sheet with low stock item.

✅ Trigger workflow manually.

✅ Show owner email with Confirm/Reject links.

✅ Click Confirm → show supplier email sent.

✅ End by showing updated sheet with new log entry.