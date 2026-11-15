import json
import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .assetflow import TOOLS, ScopeError


class Gateway:
    def __init__(self, session):
        self.session = session

    async def tool(self, name, args):
        if name not in TOOLS:
            raise ScopeError("Tool not allowed")
        result = await self.session.call_tool(
            name, {"cycle_id": args.cycle_id, "item_id": args.item_id}
        )
        if result.isError:
            raise ScopeError("MCP evidence access failed")
        # FastMCP structured dict returns are also mirrored as JSON text.
        texts = [x.text for x in result.content if x.type == "text"]
        data = json.loads("".join(texts))
        if not isinstance(data, dict):
            raise ScopeError("Invalid MCP result")
        return data


@asynccontextmanager
async def gateway(token, settings):
    # Child gets only the delegated JWT and minimal runtime configuration,
    # NEVER LLM keys, database credentials or ambient AWS credentials.
    env = {
        k: os.environ[k]
        for k in ("PATH", "SYSTEMROOT", "PYTHONPATH")
        if k in os.environ
    }
    env.update(
        {
            "ASSETFLOW_TOKEN": token,
            "COPILOT_MODE": settings.mode,
            "ASSETFLOW_URL": settings.assetflow_url,
        }
    )
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "audit_copilot.mcp_server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield Gateway(session)
