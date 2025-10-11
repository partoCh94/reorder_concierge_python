"""
excel_reader.py
---------------
Reads inventory data from Excel file with columns:
item_sku, item_name, supplier_name, supplier_email,
on_hand_qty, reorder_threshold, order_qty, last_checked
"""

import pandas as pd

def read_inventory_from_excel(file_path: str):
    df = pd.read_excel(file_path)
    df.columns = [c.strip().lower() for c in df.columns]

    expected = [
        "item_sku", "item_name", "supplier_name",
        "supplier_email", "on_hand_qty",
        "reorder_threshold", "order_qty", "last_checked"
    ]

    missing = [col for col in expected if col not in df.columns]
    if missing:
        raise ValueError(f"❌ Missing expected columns: {missing}")

    print("📊 Columns found:", list(df.columns))

    inventory = []
    for _, row in df.iterrows():
        record = {
            "sku": row["item_sku"],
            "item": row["item_name"],
            "supplier": row["supplier_name"],
            "email": row["supplier_email"],
            "qty": int(row["on_hand_qty"] or 0),
            "threshold": int(row["reorder_threshold"] or 0),
            "order_qty": int(row["order_qty"] or 0),
            "last_checked": str(row["last_checked"]) if not pd.isna(row["last_checked"]) else "",
            "approved": None
        }
        inventory.append(record)

    return inventory
