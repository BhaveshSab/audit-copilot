"""Explicit synthetic transport. It is not a model or production integration."""

import copy

from .assetflow import TOOLS, ScopeError


class DemoAssetFlow:
    def __init__(self):
        self.mark = "MISSING"
        self.version = "2026-01-01T00:00:00.000Z"
        self.applied = {}

    async def close(self):
        pass

    async def me(self):
        return {"id": "demo-reviewer", "role": "ASSET_MANAGER", "name": "Demo reviewer"}

    async def item(self, args):
        if args.cycle_id != "demo-cycle" or args.item_id != "demo-item":
            raise ScopeError("Audit item not found")
        return {
            "id": "demo-item",
            "assetId": "demo-asset",
            "result": self.mark,
            "updatedAt": self.version,
        }

    async def tool(self, name, args):
        item = await self.item(args)
        if name not in TOOLS:
            raise ScopeError("Tool not allowed")
        if name == "get_audit_item":
            return item
        if name == "get_asset":
            return {
                "id": "demo-asset",
                "assetTag": "DEMO-001",
                "status": "ALLOCATED",
                "condition": "GOOD",
            }
        if name == "get_transfers":
            return {
                "items": [
                    {
                        "id": "demo-transfer",
                        "status": "APPROVED",
                        "assetId": "demo-asset",
                    }
                ]
            }
        return {"items": []}

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
        if finding_id in self.applied:
            return copy.deepcopy(self.applied[finding_id])
        item = await self.item(args)
        if expected_updated_at != item["updatedAt"]:
            raise ScopeError("Stale audit item")
        self.mark = result
        self.version = "2026-01-01T00:01:00.000Z"
        response = {
            "id": finding_id,
            "itemId": args.item_id,
            "result": result,
            "demo": True,
        }
        self.applied[finding_id] = response
        return response
