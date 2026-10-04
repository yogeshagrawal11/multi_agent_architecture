# Author: Yogesh Agrawal
"""Service MCP server.

Exposes service-request tools: checkbook, address change, credit-limit increase.
NOTE: credit-limit increase is authorization-gated UPSTREAM (RBAC in the service
agent) before this tool is ever invoked.
Run standalone: python -m mcp_servers.service_server
"""
from mcp.server.fastmcp import FastMCP

from mcp_servers._bank import bank_post

mcp = FastMCP("service")


@mcp.tool()
def request_checkbook(customer_id: str, pages: int = 25) -> dict:
    """Raise a new checkbook request for a customer_id."""
    return bank_post(f"/service/{customer_id}/checkbook", json={"pages": pages})


@mcp.tool()
def change_address(customer_id: str, new_address: str) -> dict:
    """Change the registered address for a customer_id."""
    return bank_post(f"/service/{customer_id}/address", json={"new_address": new_address})


@mcp.tool()
def increase_credit_limit(customer_id: str, new_limit: float) -> dict:
    """Increase the credit-card limit for a customer_id. Authorization is
    enforced before this is called (privileged customers only)."""
    return bank_post(f"/service/{customer_id}/credit-limit", json={"new_limit": new_limit})


@mcp.tool()
def waive_interest_charge(customer_id: str, txn_id: str = "") -> dict:
    """Waive a credit-card interest charge for a customer_id. If txn_id is empty,
    the most recent interest charge is targeted. The charge is auto-waived only
    if it is the customer's first interest charge in the last 6 months; otherwise
    the waiver is declined. Authorization (privileged customers only) is enforced
    before this is called."""
    payload = {"txn_id": txn_id} if txn_id else {}
    return bank_post(f"/service/{customer_id}/waive-interest", json=payload)


if __name__ == "__main__":
    mcp.run()
