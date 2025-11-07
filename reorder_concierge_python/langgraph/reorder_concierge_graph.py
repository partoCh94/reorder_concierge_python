# reorder_concierge_graph.py
"""
Automated Re-Order Concierge (Google Sheets + LangGraph + HITL + Logging)
Runs once at start, then repeats every 24 hours.
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import smtplib
import os
import time

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials
REORDER_SMTP_MODE="gmail"
GMAIL_ADDRESS="charkhkaar@gmail.com"
GMAIL_APP_PASSWORD="gouxrtvkgarmpazr"
REORDER_OWNER_EMAIL="charkhkaar@gmail.com"
REORDER_EXCEL_PATH="inventory_status.xlsx"
REORDER_SERVICE_ACCOUNT_FILE="D:/bootcamp/5/reorder_concierge_python/langgraph/service_account.json"
SPREADSHEET_ID="1bgubGBfhFDOTSOqF8y8HfprGbAEpsn26wRl_3m56M9E"
# ----------------------------
# Load .env file automatically
load_dotenv()
print(os.getenv("GMAIL_ADDRESS"))
print(os.getenv("SPREADSHEET_ID"))
# ----------------------------
# Config (from environment variables)
SMTP_MODE = os.getenv("REORDER_SMTP_MODE", "local")  # "local" or "gmail"
LOCAL_SMTP_HOST = os.getenv("REORDER_LOCAL_SMTP_HOST", "localhost")
LOCAL_SMTP_PORT = int(os.getenv("REORDER_LOCAL_SMTP_PORT", "1025"))
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
REORDER_OWNER_EMAIL = os.getenv("REORDER_OWNER_EMAIL", "owner@example.com")

# Google Sheets config
SERVICE_ACCOUNT_FILE = os.getenv(
    "REORDER_SERVICE_ACCOUNT_FILE",
    r"reorder_concierge_python/langgraph/service_account.json"
)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")  # must be set in .env

# ----------------------------
# Define workflow state
class InventoryState(TypedDict):
    item: str
    qty: int
    threshold: int
    supplier: str
    email: str
    last_checked: str

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
    return state

def create_purchase_order(state: InventoryState) -> InventoryState:
    if state["qty"] < state["threshold"]:
        print(f"🧾 Auto-order created for {state['supplier']} ({state['item']} × {state['threshold'] * 2})")
        state["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        print("❌ Stock sufficient. No order created.")
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
# Google Sheets helpers
def init_sheets_client():
    if not SPREADSHEET_ID:
        raise RuntimeError("SPREADSHEET_ID not set in environment (.env)")
    sa_path = Path(SERVICE_ACCOUNT_FILE)
    if not sa_path.exists():
        raise RuntimeError(f"Service account file not found: {sa_path}")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(str(sa_path), scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)
    return sheet

def update_google_sheet_last_checked(sheet, sent_supplier_emails, now_str):
    try:
        ws = sheet.sheet1
        records = ws.get_all_records()
        header = ws.row_values(1)
        def col_index(col_name):
            try:
                return header.index(col_name) + 1
            except ValueError:
                return None

        idx_supplier = col_index("supplier_email")
        idx_onhand = col_index("on_hand_qty")
        idx_threshold = col_index("reorder_threshold")
        idx_last_checked = col_index("last_checked")

        if None in (idx_supplier, idx_onhand, idx_threshold, idx_last_checked):
            print("⚠️ Missing required columns; cannot update last_checked.")
            return

        for i, row in enumerate(records, start=2):
            supplier_email = row.get("supplier_email", "").strip()
            try:
                on_hand = int(row.get("on_hand_qty") or 0)
                threshold = int(row.get("reorder_threshold") or 0)
            except Exception:
                on_hand = 0
                threshold = 0

            if supplier_email in sent_supplier_emails and on_hand < threshold:
                ws.update_cell(i, idx_last_checked, now_str)

        try:
            log_ws = sheet.worksheet("Log")
        except gspread.exceptions.WorksheetNotFound:
            log_ws = sheet.add_worksheet(title="Log", rows=1000, cols=10)
            log_ws.append_row(["timestamp", "action", "details"])
        log_ws.append_row([now_str, "Emails sent", ", ".join(sent_supplier_emails)])
        print("✅ Google Sheet updated (last_checked + Log).")
    except Exception as e:
        print(f"❌ Failed to update Google Sheet: {e}")

# ----------------------------
# Generate emails from Google Sheet
def generate_reorder_emails_from_sheet(sheet_client, sheet_name="Sheet1"):
    try:
        worksheet = sheet_client.worksheet(sheet_name)
        records = worksheet.get_all_records()
        print(f"📧 Loaded {len(records)} records from Google Sheet for email generation.")
    except Exception as e:
        print(f"⚠️ Cannot read Google Sheet for emails: {e}")
        return []

    emails = []
    for row in records:
        if not row.get("supplier_email") or not row.get("item_name"):
            continue

        qty = int(row.get("on_hand_qty", 0))
        threshold = int(row.get("reorder_threshold", 0))
        if qty >= threshold:
            continue

        supplier = row.get("supplier_name")
        email = row.get("supplier_email")
        item = row.get("item_name")
        order_qty = row.get("order_qty", threshold * 2)

        subject = f"📦 Order Approval Required ({item})"
        body = f"""سلام {supplier} عزیز،

موجودی کالای "{item}" در انبار کمتر از حد آستانه ({threshold}) شده است.
لطفاً سفارش زیر را بررسی و تأیید نمایید:

کالا: {item}
تعداد سفارش پیشنهادی: {order_qty}
موجودی فعلی: {qty}

با احترام،
تیم سفارش خودکار
"""
        emails.append({
            "to": email,
            "subject": subject,
            "body": body,
        })

    print(f"📨 {len(emails)} reorder emails generated.")
    return emails

# ----------------------------
# HITL email send
GMAIL_ADDRESS="charkhkaar@gmail.com"
GMAIL_APP_PASSWORD="gouxrtvkgarmpazr"
REORDER_OWNER_EMAIL="charkhkaar@gmail.com"
def hitl_confirm_and_send(email_groups, sheet_client=None):
    if not email_groups:
        print("⚠️ No emails to process.")
        return

    confirm = input("Do you want to confirm and send these orders? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Orders rejected by owner.")
        return

    if SMTP_MODE == "gmail":
        smtp_host = "smtp.gmail.com"
        smtp_port = 465
        sender_email = GMAIL_ADDRESS
        use_ssl = True
    else:
        smtp_host = LOCAL_SMTP_HOST
        smtp_port = LOCAL_SMTP_PORT
        sender_email = REORDER_OWNER_EMAIL
        use_ssl = False

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(sender_email, GMAIL_APP_PASSWORD)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                pass
        print("✅ SMTP connection successful!")
    except Exception as e:
        print(f"❌ Failed to connect to SMTP server: {e}")
        return

    sent_to = []
    for group in email_groups:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = group["to"]
        msg['Subject'] = group["subject"]
        if REORDER_OWNER_EMAIL:
            msg['Cc'] = REORDER_OWNER_EMAIL
        msg.attach(MIMEText(group["body"], "plain"))

        try:
            if use_ssl:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(sender_email, GMAIL_APP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.send_message(msg)
            print(f"✅ Email sent to {group['to']}")
            sent_to.append(group['to'])
        except Exception as e:
            print(f"❌ Failed to send email to {group['to']}: {e}")

    # Update last_checked + log
    if sheet_client and sent_to:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        update_google_sheet_last_checked(sheet_client, sent_to, now_str)

# ----------------------------
# Core run function
def run_once():
    print("📥 Reading inventory from Google Sheet...")
    try:
        sheet_client = init_sheets_client()
        worksheet = sheet_client.worksheet("Sheet1")
        records = worksheet.get_all_records()
        print(f"✅ {len(records)} records loaded from Google Sheet.")
    except Exception as e:
        print(f"⚠️ Google Sheets unavailable: {e}")
        return

    graph = build_graph()

    # Map fields and invoke graph
    for idx, record in enumerate(records, start=2):
        print("\n===============================")
        mapped_record = {
            "item": record.get("item_name"),
            "qty": record.get("on_hand_qty"),
            "threshold": record.get("reorder_threshold"),
            "supplier": record.get("supplier_name"),
            "email": record.get("supplier_email"),
            "last_checked": record.get("last_checked"),
        }
        final_state = graph.invoke(mapped_record)
        print("🏁 Final state:", final_state)

        update_mapping = {
            "item": "item_name",
            "qty": "on_hand_qty",
            "threshold": "reorder_threshold",
            "supplier": "supplier_name",
            "email": "supplier_email",
            "last_checked": "last_checked",
        }

        for col_name, value in final_state.items():
            sheet_col = update_mapping.get(col_name)
            if not sheet_col:
                continue
            try:
                cell = worksheet.find(sheet_col)
                if cell:
                    worksheet.update_cell(idx, cell.col, value)
            except Exception as e:
                print(f"⚠️ Cannot update column '{sheet_col}': {e}")

    # Generate emails and send
    print("\n===============================")
    print("✉️ Generating HITL draft emails from Google Sheet...")
    emails = generate_reorder_emails_from_sheet(sheet_client, "Sheet1")
    hitl_confirm_and_send(emails, sheet_client=sheet_client)
    print("✅ Google Sheet updated and emails processed successfully.")

# ----------------------------
# Scheduler
if __name__ == "__main__":
    try:
        while True:
            print(f"\n=== Run started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
            run_once()
            print("✅ Run complete. Sleeping 24 hours...")
            time.sleep(86400)
    except KeyboardInterrupt:
        print("\n🛑 Exiting on user interrupt.")
