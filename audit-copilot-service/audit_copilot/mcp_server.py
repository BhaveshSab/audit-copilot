"""Official MCP SDK stdio server. No write tools, no caller-supplied URLs."""

import os

from mcp.server.fastmcp import FastMCP

from .assetflow import AssetFlow
from .config import Settings
from .demo import DemoAssetFlow
from .models import ToolArgs

mcp = FastMCP("AssetFlow scoped audit evidence")


async def read(name, cycle_id, item_id):
    settings = Settings.env()
    token = os.getenv("ASSETFLOW_TOKEN", "")
    if settings.mode == "live" and not token:
        raise ValueError("Delegated token required")
    api = (
        DemoAssetFlow()
        if settings.mode == "demo"
        else AssetFlow(settings.assetflow_url, token)
    )
    try:
        return await api.tool(name, ToolArgs(cycle_id=cycle_id, item_id=item_id))
    finally:
        await api.close()


@mcp.tool()
async def get_audit_item(cycle_id: str, item_id: str) -> dict:
    """Read the authorized item in an open cycle."""
    return await read("get_audit_item", cycle_id, item_id)


@mcp.tool()
async def get_asset(cycle_id: str, item_id: str) -> dict:
    """Read only the asset bound to this authorized audit item."""
    return await read("get_asset", cycle_id, item_id)


@mcp.tool()
async def get_allocation_history(cycle_id: str, item_id: str) -> dict:
    """Read bound asset allocation history."""
    return await read("get_allocation_history", cycle_id, item_id)


@mcp.tool()
async def get_transfers(cycle_id: str, item_id: str) -> dict:
    """Read bound asset transfers."""
    return await read("get_transfers", cycle_id, item_id)


@mcp.tool()
async def get_maintenance_history(cycle_id: str, item_id: str) -> dict:
    """Read bound asset maintenance history."""
    return await read("get_maintenance_history", cycle_id, item_id)


@mcp.tool()
async def get_activity(cycle_id: str, item_id: str) -> dict:
    """Read bound asset activity."""
    return await read("get_activity", cycle_id, item_id)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
