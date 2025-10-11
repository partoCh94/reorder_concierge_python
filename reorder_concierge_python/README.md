# 🧠 Automated Re-Order Concierge (LangGraph + HITL)

A background workflow that monitors stock and triggers human-approved reorders.
# 🧠 پروژه مدیریت سفارش خودکار (LangGraph + Excel فارسی)

این پروژه فایل اکسل فارسی را می‌خواند، موجودی را بررسی می‌کند و در صورت نیاز سفارش جدید ثبت می‌کند.



## ⚙️ How it works
1. Checks stock level vs threshold  
2. Requests human approval (simulated here)  
3. If approved → creates a Purchase Order (PO)

## ▶️ Run locally
```bash
pip install -r requirements.txt
python reorder_concierge_graph.py
