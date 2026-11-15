"""Only fixed API paths. User JWT is delegated, never elevated or persisted."""

import hashlib
import json
import re

import httpx

from .models import ToolArgs

TOOLS = {
    "get_audit_item": "Read the in-scope audit item and cycle state.",
    "get_asset": "Read the item's asset description and state.",
    "get_allocation_history": "Read that asset's allocation history.",
    "get_transfers": "Read that asset's transfer requests.",
    "get_maintenance_history": "Read that asset's maintenance history.",
    "get_activity": "Read that asset's activity log.",
}


class ScopeError(Exception):
    pass


class AssetFlow:
    def __init__(self, url: str, token: str, transport=None):
        self.http = httpx.AsyncClient(
            base_url=url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self):
        await self.http.aclose()

    async def request(self, method, path, **kwargs):
        r = await self.http.request(method, path, **kwargs)
        r.raise_for_status()
        if len(r.content) > 1_000_000:
            raise ScopeError("Upstream response exceeds budget")
        return r.json()

    async def me(self):
        return await self.request("GET", "auth/me")

    async def page(self, path, **filters):
        out = []
        for skip in range(0, 1000, 100):
            data = await self.request(
                "GET", path, params={**filters, "take": 100, "skip": skip}
            )
            rows = data["items"]
            out.extend(rows)
            if len(out) >= data["total"]:
                return out
            if not rows:
                raise ScopeError("Incomplete upstream pagination")
        raise ScopeError("History exceeds evidence budget; narrow the audit")

    async def item(self, args: ToolArgs):
        # Deliberately manager-only MVP: employees/department heads do not gain
        # broader history visibility merely by being assigned to an audit.
        me = await self.me()
        if me["role"] not in {"ADMIN", "ASSET_MANAGER"}:
            raise ScopeError("Manager access required")
        cycle = await self.request("GET", f"audits/{args.cycle_id}")
        if cycle["status"] != "OPEN":
            raise ScopeError("Audit cycle is closed")
        rows = await self.page(f"audits/{args.cycle_id}/items")
        item = next((x for x in rows if x["id"] == args.item_id), None)
        if item is None:
            raise ScopeError("Audit item not found")
        return item

    async def tool(self, name: str, args: ToolArgs):
        if name not in TOOLS:
            raise ScopeError("Tool not allowed")
        item = await self.item(args)
        asset_id = item["assetId"]
        if name == "get_audit_item":
            data = item
        elif name == "get_asset":
            data = await self.request("GET", f"assets/{asset_id}")
        elif name == "get_allocation_history":
            data = {
                "items": (await self.request("GET", f"assets/{asset_id}/history"))[
                    "allocations"
                ]
            }
        elif name == "get_maintenance_history":
            data = {
                "items": (await self.request("GET", f"assets/{asset_id}/history"))[
                    "maintenance"
                ]
            }
        elif name == "get_transfers":
            data = {"items": await self.page("transfers", assetId=asset_id)}
        else:
            data = {
                "items": await self.page(
                    "activity", entityType="Asset", entityId=asset_id
                )
            }
        # Project fields and redact common credential patterns before LLM egress.
        # Notes remain untrusted and may contain sensitive data; this is not DLP.
        return project(data)

    async def apply(
        self,
        args,
        finding_id,
        expected_updated_at,
        result,
        note,
        evidence_ids,
        policy_ids,
    ):
        return await self.request(
            "POST",
            f"audits/{args.cycle_id}/items/{args.item_id}/copilot-decisions",
            json={
                "idempotencyKey": finding_id,
                "expectedUpdatedAt": expected_updated_at,
                "result": result,
                "notes": note,
                "evidenceRefs": evidence_ids,
                "policyRefs": policy_ids,
            },
        )


ALLOWED = {
    "id",
    "assetId",
    "assetTag",
    "name",
    "status",
    "condition",
    "result",
    "updatedAt",
    "auditedAt",
    "createdAt",
    "allocatedAt",
    "returnedAt",
    "expectedReturnDate",
    "approvedAt",
    "resolvedAt",
    "requestedAt",
    "completedAt",
    "fromAllocationId",
    "toUserId",
    "holderUserId",
    "location",
    "items",
    "asset",
    "action",
    "entityId",
    "entityType",
    "auditCycleId",
    "notes",
    "description",
}


def project(value):
    if isinstance(value, dict):
        return {k: project(v) for k, v in value.items() if k in ALLOWED}
    if isinstance(value, list):
        if len(value) > 1000:
            raise ScopeError("Evidence array exceeds budget")
        return [project(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*)\S+",
            r"\1[REDACTED]",
            value,
        )
        value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        if len(value) > 2000:
            raise ScopeError("Evidence field exceeds budget")
        return value
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
