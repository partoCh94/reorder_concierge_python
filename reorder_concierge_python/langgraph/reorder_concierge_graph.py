"""
Automated Re-Order Concierge (Excel + LangGraph + HITL)
Safe local test version:
- uses Path resolution to avoid invalid escape sequences
- verifies Excel exists before reading
- default sends via local SMTP DebuggingServer (localhost:1025) for testing
- optional Gmail mode (uses env vars GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict
from excel_reader import read_inventory_from_excel
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import os
import sys

# ----------------------------
# Config: change these if needed
# By default we use local debug SMTP server at localhost:1025
SMTP_MODE = os.getenv("REORDER_SMTP_MODE", "local")  # "local" or "gmail"
LOCAL_SMTP_HOST = os.getenv("REORDER_LOCAL_SMTP_HOST", "localhost")
LOCAL_SMTP_PORT = int(os.getenv("REORDER_LOCAL_SMTP_PORT", "1025"))
# For Gmail mode, set env vars: GMAIL_ADDRESS and GMAIL_APP_PASSWORD

# ----------------------------
# Define the workflow state
class InventoryState(TypedDict):
    item: str
    qty: int
    threshold: int
    supplier: str
    email: str
    last_checked: str
    approved: bool | None

# ----------------------------
# State functions
def check_inventory(state: InventoryState) -> InventoryState:
    print(f"🔍 Checking item: {state['item']} (Qty={state['qty']}, Threshold={state['threshold']})")
    if state["qty"] < state["threshold"]:
        print("⚠️  Stock below threshold.")
    else:
        print("✅ Stock sufficient.")
    return state

def request_approval(state: InventoryState) -> InventoryState:
    if state["qty"] < state["threshold"]:
        print(f"📨 Requesting approval from {state['email']} (simulation)...")
        state["approved"] = True
    return state

def create_purchase_order(state: InventoryState) -> InventoryState:
    if state.get("approved"):
        print(f"🧾 Auto-order created for {state['supplier']} ({state['item']} × {state['threshold'] * 2})")
        state["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        print("❌ Approval not received. Order not created.")
    return state

def build_graph():
    workflow = StateGraph(InventoryState)
    workflow.add_node("check_inventory", check_inventory)
    workflow.add_node("request_approval", request_approval)
    workflow.add_node("create_purchase_order", create_purchase_order)
    workflow.set_entry_point("check_inventory")
    workflow.add_edge("check_inventory", "request_approval")
    workflow.add_edge("request_approval", "create_purchase_order")
    workflow.add_edge("create_purchase_order", END)
    return workflow.compile()

# ----------------------------
# HITL email generation (only items with on_hand_qty < reorder_threshold AND last_checked > 24h)
def generate_reorder_emails(file_path: Path):
    """
    Generate draft emails for order approval (HITL stage)
    Only items that:
    1) on_hand_qty < reorder_threshold
    2) last_checked > 24 hours ago (or last_checked empty/invalid)
    will be processed.
    """
    df = pd.read_excel(file_path)

    # Filter items below reorder threshold
    reorder_items = df[df["on_hand_qty"] < df["reorder_threshold"]]

    # Filter items last checked more than 24 hours ago
    now = datetime.now()
    def is_due(row):
        try:
            last_checked = pd.to_datetime(row["last_checked"])
            return (now - last_checked) > timedelta(hours=24)
        except Exception:
            return True  # if empty/invalid, treat as due

    reorder_items = reorder_items[reorder_items.apply(is_due, axis=1)]

    if reorder_items.empty:
        print("✅ No items require reordering (after 24h filter).")
        return []

    # Group by supplier
    grouped = reorder_items.groupby(["supplier_name", "supplier_email"])
    emails = []

    for (supplier_name, supplier_email), group in grouped:
        items_text = "\n".join([
            f"- {row['item_name']} (SKU: {row['item_sku']}) → On-hand: {row['on_hand_qty']}, Threshold: {row['reorder_threshold']}, Suggested order: {row['order_qty']}"
            for _, row in group.iterrows()
        ])

        body = f"""Hello {supplier_name},

Please review and approve the following items:

{items_text}

Best regards,
Automated Reorder Team
"""

        msg = MIMEMultipart()
        msg['To'] = supplier_email
        # include owner in subject so it's clear (we'll cc owner when sending)
        msg['Subject'] = f"📦 Order Approval Required ({supplier_name})"
        # store owner email in a header for later (if available in df we can pick first owner)
        emails.append({"msg": msg, "supplier_name": supplier_name, "supplier_email": supplier_email, "body": body})

    print(f"📧 {len(emails)} draft email groups generated (HITL).")
    return emails

# ----------------------------
# HITL confirmation and send (supports local debug SMTP and Gmail)
def hitl_confirm_and_send(email_groups, excel_path: Path):
    if not email_groups:
        print("⚠️ No emails to process.")
        return

    confirm = input("Do you want to confirm and send these orders? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Orders rejected by owner.")
        return

    # For sending, determine mode
    if SMTP_MODE == "gmail":
        sender_email = os.getenv("GMAIL_ADDRESS")
        app_password = os.getenv("GMAIL_APP_PASSWORD")
        if not sender_email or not app_password:
            print("❌ Gmail credentials not set in environment variables (GMAIL_ADDRESS / GMAIL_APP_PASSWORD).")
            return
        use_ssl = True
        smtp_host = "smtp.gmail.com"
        smtp_port = 465
    else:
        # local debug server
        sender_email = os.getenv("REORDER_OWNER_EMAIL", "owner@example.com")
        app_password = None
        smtp_host = LOCAL_SMTP_HOST
        smtp_port = LOCAL_SMTP_PORT
        use_ssl = False  # DebuggingServer uses plain SMTP

    sent_to = []
    for group in email_groups:
        supplier_email = group["supplier_email"]
        supplier_name = group["supplier_name"]
        body = group["body"]
        subject = f"📦 Order Approval Required ({supplier_name})"

        # prepare MIME
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = supplier_email
        msg['Subject'] = subject
        # CC owner if provided via env (optional)
        owner_email = os.getenv("REORDER_OWNER_EMAIL")
        if owner_email:
            msg['Cc'] = owner_email
        msg.attach(MIMEText(body, "plain"))

        try:
            if SMTP_MODE == "gmail":
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(sender_email, app_password)
                    server.send_message(msg)
            else:
                # local debug server (no auth)
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.send_message(msg)
            print(f"✅ (simulated) Order sent to {supplier_email}")
            sent_to.append(supplier_email)
        except Exception as e:
            print(f"❌ Failed to send email to {supplier_email}: {e}")

    # Update last_checked in Excel for rows that were sent
    if sent_to:
        df = pd.read_excel(excel_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for supplier_email in sent_to:
            mask = (df["supplier_email"] == supplier_email) & (df["on_hand_qty"] < df["reorder_threshold"])
            df.loc[mask, "last_checked"] = now
        df.to_excel(excel_path, index=False)
        print("✅ Excel file updated with new last_checked timestamps.")
    else:
        print("⚠️ No successful sends; Excel not updated.")

# ----------------------------
# Helper: resolve file path safely
def resolve_path(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        # resolve relative to script directory
        p = (Path(__file__).parent / p).resolve()
    return p

# ----------------------------
# Main
if __name__ == "__main__":
    # Put your excel filename here (relative to this script) or absolute path
    FILE_PATH_STR = os.getenv("REORDER_EXCEL_PATH", "inventory_status_farsi.xlsx")
    FILE_PATH = resolve_path(FILE_PATH_STR)

    # quick sanity checks
    if not FILE_PATH.exists():
        print(f"❌ Excel file not found: {FILE_PATH}")
        print("Make sure the file exists and path is correct (use absolute path or place file next to this script).")
        sys.exit(1)

    print("📥 Reading inventory from Excel...")
    # use your excel_reader (it should return records for the graph)
    records = read_inventory_from_excel(str(FILE_PATH))

    graph = build_graph()
    for record in records:
        print("\n===============================")
        final_state = graph.invoke(record)
        print("🏁 Final state:", final_state)

    print("\n===============================")
    print("✉️ Generating HITL draft emails...")
    emails = generate_reorder_emails(FILE_PATH)

    # HITL confirmation & sending (local debug by default)
    hitl_confirm_and_send(emails, FILE_PATH)
