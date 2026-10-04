# Author: Yogesh Agrawal
"""Mock Bank API (FastAPI + SQLite).

Simulates the bank's internal APIs (balance, transactions, service requests).
MCP servers call these endpoints; they never touch the DB directly.

All endpoints require an explicit customer_id — the real security (ensuring a
customer only sees their own data) is enforced upstream in the gateway via JWT.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import get_settings

app = FastAPI(title="Mock Bank API", version="1.0.0")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().bank_db)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# ---------- Accounts domain ----------

@app.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    with _db() as c:
        row = c.execute(
            "SELECT customer_id,name,role,registered_address,phone,email "
            "FROM customers WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="customer not found")
    return dict(row)


@app.get("/accounts/{customer_id}")
def list_accounts(customer_id: str) -> dict:
    with _db() as c:
        rows = c.execute(
            "SELECT account_id,type,balance FROM accounts WHERE customer_id=?",
            (customer_id,),
        ).fetchall()
    return {"customer_id": customer_id, "accounts": [dict(r) for r in rows]}


@app.get("/balance/{customer_id}")
def get_balance(customer_id: str) -> dict:
    with _db() as c:
        rows = c.execute(
            "SELECT account_id,type,balance FROM accounts WHERE customer_id=?",
            (customer_id,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="no accounts for customer")
    return {
        "customer_id": customer_id,
        "balances": [
            {"account_id": r["account_id"], "type": r["type"], "balance": r["balance"]}
            for r in rows
        ],
    }


# ---------- Transactions domain ----------

@app.get("/transactions/{customer_id}")
def list_transactions(customer_id: str, limit: int = 5) -> dict:
    with _db() as c:
        rows = c.execute(
            "SELECT t.txn_id,t.account_id,t.date,t.amount,t.direction,t.merchant,"
            "t.category,t.flagged_suspicious,t.waived FROM transactions t "
            "JOIN accounts a ON a.account_id=t.account_id "
            "WHERE a.customer_id=? ORDER BY t.date DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    return {"customer_id": customer_id, "transactions": [dict(r) for r in rows]}


class FlagRequest(BaseModel):
    txn_id: str


@app.post("/transactions/{customer_id}/flag")
def flag_transaction(customer_id: str, req: FlagRequest) -> dict:
    with _db() as c:
        owned = c.execute(
            "SELECT 1 FROM transactions t JOIN accounts a ON a.account_id=t.account_id "
            "WHERE a.customer_id=? AND t.txn_id=?",
            (customer_id, req.txn_id),
        ).fetchone()
        if not owned:
            raise HTTPException(status_code=404, detail="transaction not found")
        c.execute(
            "UPDATE transactions SET flagged_suspicious=1 WHERE txn_id=?",
            (req.txn_id,),
        )
        c.commit()
    return {"txn_id": req.txn_id, "flagged_suspicious": True}


@app.get("/transactions/{customer_id}/flagged")
def list_flagged(customer_id: str) -> dict:
    with _db() as c:
        rows = c.execute(
            "SELECT t.txn_id,t.date,t.amount,t.merchant FROM transactions t "
            "JOIN accounts a ON a.account_id=t.account_id "
            "WHERE a.customer_id=? AND t.flagged_suspicious=1 ORDER BY t.date DESC",
            (customer_id,),
        ).fetchall()
    return {"customer_id": customer_id, "flagged": [dict(r) for r in rows]}


# ---------- Service domain ----------

class CheckbookRequest(BaseModel):
    pages: int = 25


@app.post("/service/{customer_id}/checkbook")
def request_checkbook(customer_id: str, req: CheckbookRequest) -> dict:
    return _create_request(customer_id, "checkbook", {"pages": req.pages}, "open")


class AddressChangeRequest(BaseModel):
    new_address: str


@app.post("/service/{customer_id}/address")
def change_address(customer_id: str, req: AddressChangeRequest) -> dict:
    with _db() as c:
        exists = c.execute(
            "SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="customer not found")
        c.execute(
            "UPDATE customers SET registered_address=? WHERE customer_id=?",
            (req.new_address, customer_id),
        )
        c.commit()
    return _create_request(
        customer_id, "address_change", {"new_address": req.new_address}, "completed"
    )


class CreditLimitRequest(BaseModel):
    new_limit: float


@app.post("/service/{customer_id}/credit-limit")
def increase_credit_limit(customer_id: str, req: CreditLimitRequest) -> dict:
    """Increase credit limit. Authorization (role check) is enforced upstream
    (service agent / RBAC) BEFORE this endpoint is ever called."""
    with _db() as c:
        card = c.execute(
            "SELECT card_id FROM credit_cards WHERE customer_id=?", (customer_id,)
        ).fetchone()
        if not card:
            raise HTTPException(status_code=404, detail="no credit card for customer")
        c.execute(
            'UPDATE credit_cards SET "limit"=? WHERE customer_id=?',
            (req.new_limit, customer_id),
        )
        c.commit()
    return _create_request(
        customer_id, "credit_limit", {"new_limit": req.new_limit}, "completed"
    )


class WaiveInterestRequest(BaseModel):
    txn_id: str | None = None  # if omitted, waive the most recent interest charge


def _add_months(d: date, months: int) -> date:
    """Return date `months` before/after d (months may be negative)."""
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # clamp day to end of month
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                      else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


@app.post("/service/{customer_id}/waive-interest")
def waive_interest(customer_id: str, req: WaiveInterestRequest) -> dict:
    """Waive a credit-card interest charge.

    Business rule (applied here, not in the agent): a charge is auto-waived only
    if it is the customer's FIRST interest charge in the last 6 months — i.e.
    there is NO other interest charge in the 6 months immediately before it.
    Otherwise the waive is declined.

    Authorization (privileged-only) is enforced UPSTREAM via RBAC before this
    endpoint is ever called.
    """
    with _db() as c:
        charges = c.execute(
            "SELECT t.txn_id,t.date,t.amount,t.waived FROM transactions t "
            "JOIN accounts a ON a.account_id=t.account_id "
            "WHERE a.customer_id=? AND t.category='interest_charge' "
            "ORDER BY t.date DESC",
            (customer_id,),
        ).fetchall()

        if not charges:
            raise HTTPException(status_code=404, detail="no interest charge found")

        # Pick the target charge: explicit txn_id if it matches, else the most
        # recent interest charge. (If the caller passed an unknown/placeholder
        # id, fall back to the most recent rather than failing — the intent is
        # clearly "waive my interest charge".)
        target = None
        if req.txn_id:
            target = next((r for r in charges if r["txn_id"] == req.txn_id), None)
        if target is None:
            target = charges[0]

        if target["waived"] == 1:
            return {"txn_id": target["txn_id"], "waived": True,
                    "reason": "This interest charge was already waived."}

        target_date = date.fromisoformat(target["date"])
        window_start = _add_months(target_date, -6)

        # Any OTHER interest charge within the 6 months before the target?
        prior = [
            r for r in charges
            if r["txn_id"] != target["txn_id"]
            and window_start <= date.fromisoformat(r["date"]) < target_date
        ]

        if prior:
            return {
                "txn_id": target["txn_id"],
                "amount": target["amount"],
                "waived": False,
                "reason": (
                    "Not eligible for automatic waiver: there is already another "
                    "interest charge in the last 6 months."
                ),
            }

        c.execute("UPDATE transactions SET waived=1 WHERE txn_id=?", (target["txn_id"],))
        c.commit()

    _create_request(customer_id, "interest_waiver",
                    {"txn_id": target["txn_id"], "amount": target["amount"]}, "completed")
    return {
        "txn_id": target["txn_id"],
        "amount": target["amount"],
        "waived": True,
        "reason": "First interest charge in the last 6 months — automatically waived.",
    }


def _create_request(customer_id: str, rtype: str, payload: dict, status: str) -> dict:
    req_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    import json
    with _db() as c:
        c.execute(
            "INSERT INTO service_requests (req_id,customer_id,type,status,"
            "payload_json,created_at) VALUES (?,?,?,?,?,?)",
            (req_id, customer_id, rtype, status, json.dumps(payload), now),
        )
        c.commit()
    return {"req_id": req_id, "type": rtype, "status": status, "payload": payload}
