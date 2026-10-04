# Author: Yogesh Agrawal
"""Transactions MCP server.

Exposes transaction listing/flagging tools.
Run standalone: python -m mcp_servers.transactions_server
"""
from mcp.server.fastmcp import FastMCP

from mcp_servers._bank import bank_get, bank_post

mcp = FastMCP("transactions")


@mcp.tool()
def list_transactions(customer_id: str, limit: int = 5) -> dict:
    """List the most recent transactions for a customer_id (default 5)."""
    return bank_get(f"/transactions/{customer_id}", params={"limit": limit})


@mcp.tool()
def get_last_transaction(customer_id: str) -> dict:
    """Get the single most recent transaction for a customer_id."""
    data = bank_get(f"/transactions/{customer_id}", params={"limit": 1})
    txns = data.get("transactions", [])
    return {"customer_id": customer_id, "transaction": txns[0] if txns else None}


@mcp.tool()
def flag_transaction_suspicious(customer_id: str, txn_id: str) -> dict:
    """Flag a transaction as suspicious for a customer_id."""
    return bank_post(f"/transactions/{customer_id}/flag", json={"txn_id": txn_id})


@mcp.tool()
def check_flagged(customer_id: str) -> dict:
    """List transactions the customer previously flagged as suspicious."""
    return bank_get(f"/transactions/{customer_id}/flagged")


if __name__ == "__main__":
    mcp.run()
