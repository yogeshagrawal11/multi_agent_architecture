# Author: Yogesh Agrawal
"""Accounts MCP server.

Exposes account/balance tools. Decoupled from agents via MCP (stdio transport).
Run standalone: python -m mcp_servers.accounts_server
"""
from mcp.server.fastmcp import FastMCP

from mcp_servers._bank import bank_get

mcp = FastMCP("accounts")


@mcp.tool()
def get_balance(customer_id: str) -> dict:
    """Get the account balance(s) for a given customer_id."""
    return bank_get(f"/balance/{customer_id}")


@mcp.tool()
def get_account_info(customer_id: str) -> dict:
    """Get the list of accounts (id, type, balance) for a customer_id."""
    return bank_get(f"/accounts/{customer_id}")


if __name__ == "__main__":
    mcp.run()
