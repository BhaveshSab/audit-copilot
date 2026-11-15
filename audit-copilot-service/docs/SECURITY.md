# Security boundaries and explicit limitations

## Boundaries implemented

- Delegated user JWT, revalidated through AssetFlow on every HTTP request. No admin-at-signup, service-role substitution or model credential access.
- Conservative manager-only MVP: employee/department-head tool use is denied, not silently elevated. Native AssetFlow scope/guards remain authoritative.
- The tool caller supplies only cycle/item IDs. Server derives the asset ID from the authorized audit item. No model-selected URL, SQL, shell command or write tool.
- Child MCP process receives the delegated JWT and minimal config, not LLM keys, database DSNs or AWS credentials. Its stdio transport is local, not a public unauthenticated MCP HTTP endpoint.
- Tools project fields and remove common credential patterns. Arbitrary free text can still contain sensitive information; projection/redaction is **not comprehensive DLP**. Live model egress needs operator/data-owner approval.
- All model content is untrusted and schema validated. Prompt injection cannot add capabilities to these interfaces, but can still corrupt the interpretation of permitted data. Human review is mandatory.
- Evidence and policy references and verbatim quotes are checked against actual collected sources; no claim of semantic entailment or calibrated confidence.
- Per-investigation 90-second wall budget (including MCP initialization), six LLM attempts, 60,000 serialized input characters and 1,600 requested output tokens per generation. Provider-specific thinking/token billing may differ. Four concurrent investigations and ten starts/user/minute per process. These are **single-process controls**, not a distributed spend cap.
- Failover only for configured transient errors; authentication/schema failures are not retried. Keys use headers, not query strings.
- App reviewer must own the proposal and retain manager permissions. Refused/expired/rejected proposals cannot be applied. Review requires a nonempty human note.
- All fetched context is compared before the first apply attempt. AssetFlow checks `AuditItem.updatedAt` under a cycle lock when writing, atomically records a per-actor idempotency receipt, provenance activity row and existing discrepancy in-app notifications. Reusing a key with another body conflicts. Unknown write responses retry with the SAME stored body/key.
- Repeat receipts can be read after cycle closure without a second mutation; authorization is rechecked first. Application approval is separate from closure; this endpoint never closes an audit or changes asset lifecycle state itself.
- Context verification and backend write are not a cross-service serializable snapshot: an allocation/transfer may change between them. The atomic freshness check covers the audit item, not every related row. Review promptly; stronger global evidence-versioning is future work.
- SQLite journal stores no JWTs or LLM keys and is mode 0600. It DOES contain evidence/notes and is not encrypted or tamper-proof. Use restricted storage, encrypted disks, backups, access review and retention before real data. Internal audit events are append-only through this app, not cryptographic attestations.
- No CORS allowance or cookie-based authentication. Integrated frontend uses an explicit same-origin reverse proxy and bearer header. TLS is required for non-local fixed upstreams; do not put private keys into frontend build variables.

## Out of scope / not claimed

- Autonomous write approval, production readiness, multi-tenancy, legal compliance certification.
- Authentication of external MCP network clients: only stdio is implemented.
- Telegram review, automatic AuditCycle-open hooks, PDF/OCR ingestion, cross-encoder reranking.
- BM25: retrieval uses PostgreSQL `ts_rank_cd`, cosine distance and reciprocal-rank fusion.
- Guaranteed hallucination prevention, superiority of multi-agent architecture, real-auditor evaluation.
- Exact-once network delivery. The database mutation/receipt is idempotent; a crashed caller may have an unknown response until the identical request is retried.

## Rollout safety

Nothing in this change deploys, migrates production, broadens IAM, opens AWS ingress, enables jobs or allocates paid resources. Existing local uncommitted infra changes were left intact. Inspect the new migration and take a recoverable off-host backup before any production schema change. Do not run destructive reset commands on real databases.
