import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from .agents import FixtureLLM, investigate
from .assetflow import AssetFlow, ScopeError, digest
from .config import Settings
from .demo import DemoAssetFlow
from .mcp_client import gateway
from .models import Investigate, Review, ToolArgs
from .providers import LLM
from .retrieval import DemoRetrieval, OpenAIEmbedder, PgRetrieval
from .store import StateConflict, Store


@dataclass
class Context:
    user: dict
    api: object
    token: str


def create_app(
    settings=None,
    *,
    api_factory=None,
    llm_factory=None,
    retrieval=None,
    gateway_factory=None,
):
    s = settings or Settings.env()
    store = Store(s.state_path)
    demo = DemoAssetFlow()
    retrieval = retrieval or (
        DemoRetrieval()
        if s.mode == "demo"
        else PgRetrieval(
            s.database_url,
            OpenAIEmbedder(
                os.getenv("OPENAI_API_KEY", ""), s.embedding_model, s.embedding_dim
            ),
        )
    )
    app = FastAPI(title="AssetFlow Audit Copilot", version="0.1.0", docs_url="/docs")
    app.state.store = store
    app.state.demo = demo
    slots = asyncio.Semaphore(4)
    recent = {}

    @app.middleware("http")
    async def safety(request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > 16000:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        try:
            response = await call_next(request)
        except Exception:
            # Do not expose upstream bodies/URLs, prompts, tokens or SQL errors.
            return JSONResponse(
                {
                    "detail": "Operation failed; no successful application is implied. Retry review with the same proposal and note if its state is APPLYING."
                },
                status_code=502,
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    async def auth(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer ") or len(authorization) > 8192:
            raise HTTPException(401, "Bearer token required")
        token = authorization[7:]
        if s.mode == "demo":
            if token != "demo":
                raise HTTPException(401, "Demo token is demo")
            api = demo
        else:
            api = (
                api_factory(token) if api_factory else AssetFlow(s.assetflow_url, token)
            )
        try:
            user = await api.me()
            if user.get("role") not in {"ADMIN", "ASSET_MANAGER"}:
                raise HTTPException(403, "Manager access required")
            yield Context(user, api, token)
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                e.response.status_code
                if e.response.status_code in {401, 403, 404, 409}
                else 502,
                "AssetFlow rejected the operation",
            ) from None
        except ScopeError:
            raise HTTPException(
                409, "Scope, cycle or evidence changed; reinvestigate"
            ) from None
        finally:
            await api.close()

    @app.exception_handler(KeyError)
    async def missing(_, exc):
        return JSONResponse({"detail": "Finding not found"}, status_code=404)

    @app.exception_handler(StateConflict)
    async def conflict(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": s.mode, "live_llm_verified": False}

    @app.get("/api/findings")
    async def list_findings(c: Context = Depends(auth)):
        return store.list(c.user["id"])

    @app.post("/api/investigations", status_code=201)
    async def start(req: Investigate, c: Context = Depends(auth)):
        if slots.locked():
            raise HTTPException(429, "Investigation concurrency budget exhausted")
        now = time.monotonic()
        times = [t for t in recent.get(c.user["id"], []) if now - t < 60]
        if len(times) >= 10:
            raise HTTPException(429, "Per-user investigation budget exhausted")
        recent[c.user["id"]] = times + [now]
        async with slots:
            llm = (
                llm_factory()
                if llm_factory
                else (FixtureLLM() if s.mode == "demo" else LLM(s))
            )

            @asynccontextmanager
            async def local_gateway():
                yield c.api

            factory = gateway_factory or (
                lambda token, settings: (
                    local_gateway() if s.mode == "demo" else gateway(token, settings)
                )
            )
            started = time.monotonic()
            async with asyncio.timeout(s.max_seconds):
                async with factory(c.token, s) as tools:
                    data = await investigate(req, tools, retrieval, llm, s.max_seconds)
            # Evidence was collected via the tool boundary, not another token.
            item_evidence = next(
                e["data"] for e in data["evidence"] if e["tool"] == "get_audit_item"
            )
            data.update(
                {
                    "request": req.model_dump(),
                    "item_updated_at": item_evidence["updatedAt"],
                    "mode": s.mode,
                    "elapsed_seconds": time.monotonic() - started,
                    "usage": getattr(getattr(llm, "budget", None), "usage", []),
                    "verification": "fixture-only"
                    if s.mode == "demo"
                    else "live-provider-output-not-independently-adjudicated",
                }
            )
            return store.create(c.user["id"], data)

    @app.get("/api/findings/{fid}")
    async def get_finding(fid: str, c: Context = Depends(auth)):
        return store.get(fid, c.user["id"])

    @app.post("/api/findings/{fid}/review")
    async def review(fid: str, req: Review, c: Context = Depends(auth)):
        row = store.get(fid, c.user["id"])
        payload = row["payload"]
        f = payload["finding"]
        if row["state"] == "APPLIED":
            if row["review"] != req.model_dump():
                raise StateConflict("Decision already applied with a different review")
            return row
        if row["state"] == "APPLYING" and row["review"] != req.model_dump():
            raise StateConflict("Retry must use the original approval and note")
        if time.time() - row["created"] > 86400 and row["state"] != "APPLYING":
            raise StateConflict("Proposal expired; reinvestigate")
        if req.action == "reject":
            store.transition(
                fid, c.user["id"], {"AWAITING_REVIEW"}, "REJECTED", req.model_dump()
            )
            return store.get(fid, c.user["id"])
        if f["refused"] or f["result"] is None:
            raise StateConflict("Refused findings cannot be applied")
        args = ToolArgs(
            cycle_id=payload["request"]["cycle_id"],
            item_id=payload["request"]["item_id"],
        )
        if row["state"] != "APPLYING":
            if row["state"] != "AWAITING_REVIEW":
                raise StateConflict("Finding is not awaiting review")
            # Reject stale fetched context before the first write attempt.
            for old in payload["evidence"]:
                if digest(await c.api.tool(old["tool"], args)) != digest(old["data"]):
                    raise StateConflict("Evidence changed; reinvestigate")
            store.transition(
                fid, c.user["id"], {"AWAITING_REVIEW"}, "APPLYING", req.model_dump()
            )
        # Persist APPLYING before I/O. An ambiguous response is retryable using
        # the identical server-side idempotency key/body, never a new key.
        receipt = await c.api.apply(
            args,
            fid,
            payload["item_updated_at"],
            f["result"],
            req.note,
            f["evidence_ids"],
            [r["clause_id"] for r in f["policy_refs"]],
        )
        store.transition(
            fid,
            c.user["id"],
            {"APPLYING", "APPLIED"},
            "APPLIED",
            req.model_dump(),
            receipt,
        )
        return store.get(fid, c.user["id"])

    ui = Path(__file__).resolve().parents[1] / "ui" / "dist"
    if ui.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=ui, html=True), name="review-ui")
    return app
