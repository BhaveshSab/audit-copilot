"""Called ONLY by the disposable integration runner, never production."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

from .agents import FixtureLLM
from .assetflow import TOOLS, ScopeError
from .mcp_client import gateway
from .models import ToolArgs
from .app import create_app
from .config import Settings
from .models import Clause
from .retrieval import CORPUS, PgRetrieval, local_vector


class FixtureEmbedder:
    model = "local-hash-fixture-1536"

    async def embed(self, texts):
        return [local_vector(t, 1536) for t in texts]


async def main():
    s = Settings(
        mode="live",
        assetflow_url=os.environ["ASSETFLOW_URL"],
        database_url=os.environ["COPILOT_DATABASE_URL"],
    )
    retriever = PgRetrieval(s.database_url, FixtureEmbedder())
    clauses = [Clause(**c) for c in json.loads(CORPUS.read_text())]
    await retriever.ingest(clauses)
    async with gateway(os.environ["ASSETFLOW_TOKEN"], s) as tools:
        args = ToolArgs(
            cycle_id=os.environ["TEST_CYCLE"], item_id=os.environ["TEST_ITEM"]
        )
        for tool in TOOLS:
            assert isinstance(await tools.tool(tool, args), dict)
        try:
            await tools.tool(
                "get_asset",
                ToolArgs(cycle_id=os.environ["TEST_CYCLE"], item_id="wrong-item"),
            )
        except ScopeError:
            pass
        else:
            raise AssertionError("Cross-item access must be denied")
    hits = await retriever.search("missing asset custody physical presence")
    assert hits and len(hits) == 5
    with tempfile.TemporaryDirectory() as tmp:
        from dataclasses import replace

        app = create_app(
            replace(s, state_path=str(Path(tmp) / "findings.db")),
            llm_factory=FixtureLLM,
            retrieval=retriever,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://copilot.test",
            headers={"Authorization": "Bearer " + os.environ["ASSETFLOW_TOKEN"]},
        ) as c:
            response = await c.post(
                "/api/investigations",
                json={
                    "cycle_id": os.environ["TEST_CYCLE"],
                    "item_id": os.environ["TEST_ITEM"],
                    "question": "Investigate missing asset custody and human approval policy",
                },
            )
            assert response.status_code == 201, response.text
            row = response.json()
            assert row["state"] == "AWAITING_REVIEW"
            args = {
                "action": "approve",
                "note": "Human verified absence during isolated test; investigate custody.",
            }
            first = await c.post(f"/api/findings/{row['id']}/review", json=args)
            assert first.status_code == 200, first.text
            assert first.json()["state"] == "APPLIED"
            again = await c.post(f"/api/findings/{row['id']}/review", json=args)
            assert (
                again.status_code == 200
                and again.json()["receipt"] == first.json()["receipt"]
            )
            print(
                "PASS: investigation, grounded citations, human application and retry against real API/database"
            )


if __name__ == "__main__":
    asyncio.run(main())
