# Author: Yogesh Agrawal
"""Seed the mock bank SQLite DB and the session-store login users.

All values are fictional. Demonstrates the design's role scenario:
  - John  (C1): privileged  -> may increase credit limit
  - Sanjay(C2): standard    -> may NOT increase credit limit

Run: python -m mock_bank.seed
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from app.config import get_settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Demo login users (username, password, customer_id, role).
# Passwords are obviously-fake demo values.
LOGIN_USERS = [
    ("john", "password123", "C1", "privileged"),
    ("sanjay", "password123", "C2", "standard"),
    ("priya", "password123", "C3", "premium"),
    ("arjun", "password123", "C4", "standard"),
    ("meena", "password123", "C5", "premium"),
]

CUSTOMERS = [
    # customer_id, name, role, address, phone, email
    ("C1", "John Doe", "privileged", "123 Main St, Springfield, IL 62701", "+1-217-555-0101", "john@example.com"),
    ("C2", "Sanjay Kumar", "standard", "456 Oak Ave, Austin, TX 73301", "+1-512-555-0102", "sanjay@example.com"),
    ("C3", "Priya Raman", "premium", "789 Pine Rd, Seattle, WA 98101", "+1-206-555-0103", "priya@example.com"),
    ("C4", "Arjun Nair", "standard", "321 Maple Dr, Denver, CO 80202", "+1-303-555-0104", "arjun@example.com"),
    ("C5", "Meena Iyer", "premium", "654 Cedar Ln, Boston, MA 02108", "+1-617-555-0105", "meena@example.com"),
]

ACCOUNTS = [
    # account_id, customer_id, type, balance
    ("A1", "C1", "savings", 24345.0),
    ("A2", "C1", "current", 102000.0),
    ("A3", "C2", "savings", 52340.0),
    ("A4", "C3", "savings", 8750.0),
    ("A5", "C4", "savings", 15600.0),
    ("A6", "C5", "savings", 61200.0),
]

# account_id, date, amount, direction, merchant, flagged
# account_id, date, amount, direction, merchant, category, flagged
TRANSACTIONS = [
    ("A1", "2026-09-01", 1200.0, "debit", "Amazon", "purchase", 1),
    ("A1", "2026-09-03", 500.0, "debit", "Starbucks", "purchase", 0),
    ("A1", "2026-09-10", 25000.0, "credit", "Salary", "salary", 0),
    ("A1", "2026-09-15", 300.0, "debit", "Uber", "purchase", 0),
    ("A1", "2026-09-20", 2000.0, "debit", "Flipkart", "purchase", 0),
    ("A3", "2026-09-02", 800.0, "debit", "Swiggy", "purchase", 0),
    ("A3", "2026-09-08", 40000.0, "credit", "Salary", "salary", 0),
    ("A3", "2026-09-12", 1500.0, "debit", "BigBasket", "purchase", 0),
    ("A4", "2026-09-05", 250.0, "debit", "Zomato", "purchase", 0),
    ("A5", "2026-09-07", 600.0, "debit", "Reliance", "purchase", 0),
    ("A6", "2026-09-09", 3200.0, "debit", "Croma", "purchase", 0),

    # ---- Credit-card interest charges (one per customer, all users) ----
    # C1/A1: single recent interest charge -> AUTO-WAIVE eligible (first in 6 mo).
    ("A1", "2026-09-25", 450.0, "debit", "Credit Card Interest", "interest_charge", 0),
    # C2/A3: TWO interest charges within 6 months -> the recent one is DECLINED
    #        (a prior interest charge exists in the last 6 months).
    ("A3", "2026-07-20", 380.0, "debit", "Credit Card Interest", "interest_charge", 0),
    ("A3", "2026-09-18", 420.0, "debit", "Credit Card Interest", "interest_charge", 0),
    # C3/A4, C4/A5, C5/A6: single recent interest charge each (rule-eligible, but
    # these customers are premium/standard so RBAC forwards them to a representative).
    ("A4", "2026-09-22", 300.0, "debit", "Credit Card Interest", "interest_charge", 0),
    ("A5", "2026-09-23", 275.0, "debit", "Credit Card Interest", "interest_charge", 0),
    ("A6", "2026-09-24", 510.0, "debit", "Credit Card Interest", "interest_charge", 0),
]

CREDIT_CARDS = [
    # card_id, customer_id, number_masked, limit
    ("CC1", "C1", "4111 11** **** 1111", 200000.0),
    ("CC2", "C2", "4111 22** **** 2222", 100000.0),
    ("CC3", "C3", "4111 33** **** 3333", 150000.0),
]


def _init_bank(conn: sqlite3.Connection) -> None:
    # Drop then recreate from the schema. Seeding always fully repopulates the
    # demo data, so dropping is the correct idempotent behavior — and it ensures
    # the schema is always current even if an older DB (e.g. a persisted Docker
    # volume) predates a schema change such as the `category`/`waived` columns.
    for tbl in ("transactions", "accounts", "credit_cards", "service_requests", "customers"):
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
    conn.executescript(SCHEMA_PATH.read_text())

    conn.executemany(
        "INSERT INTO customers (customer_id,name,role,registered_address,phone,email) "
        "VALUES (?,?,?,?,?,?)",
        CUSTOMERS,
    )
    conn.executemany(
        "INSERT INTO accounts (account_id,customer_id,type,balance) VALUES (?,?,?,?)",
        ACCOUNTS,
    )
    conn.executemany(
        'INSERT INTO credit_cards (card_id,customer_id,number_masked,"limit") '
        "VALUES (?,?,?,?)",
        CREDIT_CARDS,
    )
    for acct, date, amount, direction, merchant, category, flagged in TRANSACTIONS:
        conn.execute(
            "INSERT INTO transactions (txn_id,account_id,date,amount,direction,"
            "merchant,category,flagged_suspicious) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), acct, date, amount, direction, merchant, category, flagged),
        )
    conn.commit()


def _init_users() -> None:
    """Seed login users into the session store (hashed passwords)."""
    from app.session import store
    from app.auth.passwords import hash_password

    store.init_db()
    import sqlite3 as _sq
    settings = get_settings()
    conn = _sq.connect(settings.sessions_db)
    conn.execute("DELETE FROM users")
    for username, password, customer_id, role in LOGIN_USERS:
        conn.execute(
            "INSERT INTO users (username,password_hash,customer_id,role) VALUES (?,?,?,?)",
            (username, hash_password(password), customer_id, role),
        )
    conn.commit()
    conn.close()


def main() -> None:
    settings = get_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    conn = sqlite3.connect(settings.bank_db)
    _init_bank(conn)
    conn.close()
    _init_users()
    print(f"[seed] bank_db={settings.bank_db} sessions_db={settings.sessions_db}")
    print(f"[seed] {len(CUSTOMERS)} customers, {len(ACCOUNTS)} accounts, "
          f"{len(TRANSACTIONS)} transactions, {len(LOGIN_USERS)} login users seeded.")


if __name__ == "__main__":
    main()
