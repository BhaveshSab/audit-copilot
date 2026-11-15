import pytest
from audit_copilot.assetflow import TOOLS, ScopeError
from audit_copilot.config import Settings
from audit_copilot.mcp_client import gateway
from audit_copilot.models import ToolArgs
from audit_copilot.retrieval import DemoRetrieval, local_vector, rrf


async def test_retrieval_and_exact_ids():
    r = DemoRetrieval()
    assert len(r.clauses) == 60
    hits = await r.search("duplicate asset tags identity verification")
    assert any(c.id.startswith("AF-06.") for c in hits)
    assert await r.search("zyxwvutsrqponmlkjihg") == []


def test_rrf():
    assert rrf(["a", "b"], ["b", "c"], 2) == ["b", "a"]
    assert local_vector("audit missing") == local_vector("audit missing")


async def test_official_mcp_stdio_roundtrip():
    async with gateway("", Settings()) as tools:
        listing = await tools.session.list_tools()
        assert {t.name for t in listing.tools} == set(TOOLS)
        args = ToolArgs(cycle_id="demo-cycle", item_id="demo-item")
        for name in TOOLS:
            assert isinstance(await tools.tool(name, args), dict)
        with pytest.raises(ScopeError):
            await tools.tool(
                "get_asset", ToolArgs(cycle_id="other", item_id="demo-item")
            )
