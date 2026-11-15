# API and AssetFlow integration contract

All copilot `/api/*` routes require `Authorization: Bearer <existing AssetFlow JWT>` (or literal `demo` only in demo mode). In live mode `/auth/me` determines identity and role. No role is trusted from request JSON or JWT decoding in the copilot.

| Copilot route | Behavior |
|---|---|
| GET `/health` | Public liveness/mode; not an assertion of live LLM acceptance |
| POST `/api/investigations` | `{cycle_id,item_id,question?}` → stored grounded proposal; 201 |
| GET `/api/findings` | Current owner's latest 100 proposal summaries |
| GET `/api/findings/{id}` | Owner-only evidence, clauses, finding, state and receipt |
| POST `/api/findings/{id}/review` | `{action:"approve"|"reject",note}`; approve applies only the stored mark |

No token is accepted from an LLM, query parameter, policy chunk or review body. Request bodies are bounded to 16 KB at the application layer; deploy a proxy body-size limit too. Investigation errors do not imply that an application succeeded. If a write response is lost, stored state remains APPLYING and retry must use the identical action/note.

## Official MCP tools

All take `{cycle_id,item_id}`. Every call rechecks manager identity, open cycle and item membership. Reads are bounded to 1,000 paginated rows and a one-megabyte upstream response; over-budget histories refuse rather than silently truncate pagination.

| MCP tool | Existing AssetFlow route(s) |
|---|---|
| get_audit_item | GET `/auth/me`, `/audits/:id`, `/audits/:id/items` |
| get_asset | Above binding, then GET `/assets/:assetId` |
| get_allocation_history | Binding, then GET `/assets/:assetId/history` → allocations |
| get_transfers | Binding, then GET `/transfers?assetId=...` |
| get_maintenance_history | Binding, then GET `/assets/:assetId/history` → maintenance |
| get_activity | Binding, then GET `/activity?entityType=Asset&entityId=...` |

Activity is Asset-entity activity, not every indirect allocation/transfer event. The separate history tools cover those domains. Payload projection can omit fields that a future finding needs; incomplete evidence must lead to refusal/review, not inference from absence.

## New AssetFlow write endpoint (companion change)

`POST /api/audits/:cycleId/items/:itemId/copilot-decisions`, ADMIN/ASSET_MANAGER only:

```
{
  "idempotencyKey": "<proposal UUID v4>",
  "expectedUpdatedAt": "<original AuditItem.updatedAt ISO timestamp>",
  "result": "VERIFIED | MISSING | DAMAGED",
  "notes": "<human review note>",
  "evidenceRefs": ["E1"],
  "policyRefs": ["AF-04.1"]
}
```

Transaction: cycle row lock → per-actor/key advisory lock → receipt check → open cycle/item binding/freshness check → mark + receipt + activity + discrepancy in-app notifications. Reject stale item (409), changed key body (409), closed cycle (409), invalid result (400), unauthorized caller (401/403), wrong cycle/item (404).

AssetFlow stores provenance references but does not independently query the copilot corpus or prove model authorship; the authenticated manager is responsible for the explicit reviewed decision. The public ordinary marking API remains available with its existing semantics.
