# Audit Copilot for AssetFlow

Evidence-grounded audit investigations with **official MCP**, **PostgreSQL full-text + pgvector retrieval**, capability-separated agents, and **explicit human review**. Includes a React review workspace and an opt-in panel inside AssetFlow's audit-item screen.

## Delivery and verification status

This service was built in `assetflow/audit-copilot/` on the existing Arena branch. It is self-contained for transfer to the empty `BhaveshSab/audit-copilot` repository. **It has not been pushed to that separate repository or deployed.** AssetFlow's companion changes remain in the current AssetFlow working tree. No production migration or LLM charge was performed.

Interpret “phases 2–5” as: **2 retrieval/corpus; 3 evidence/policy agents + orchestration; 4 adjudication + human review; 5 evaluation/ablation**. The phase-1 MCP boundary and delivery/CI essentials are included too. These are not the earlier EC2 capacity-test stages.

| Capability | Implemented | Verification |
|---|---|---|
| Six read tools, official MCP SDK stdio | Yes | Real client/server subprocess round trip; real AssetFlow integration |
| Delegated JWT / scope / read-only agent tools | Yes, ADMIN/ASSET_MANAGER MVP | Denial, binding, unknown-tool and role tests |
| 60 policy clauses | Authored **demo** corpus | Schema/ID checks; not real organizational policy |
| Hybrid PostgreSQL FTS + pgvector | Yes, reciprocal-rank fusion | Executed on PostgreSQL-WASM with actual pgvector extension and deterministic fixture embeddings |
| Semantic embeddings | OpenAI adapter | No live paid embedding call made |
| Separate evidence / policy / adjudicator capabilities | Yes | Source/quote validation, reference-denial, budget and timeout tests |
| OpenAI + Gemini, transient retry/failover | Yes | Mock HTTP contract tests; **not live-provider verification** |
| Human approval / reject / stale protection | Yes | Real API + DB test, UI tests, idempotent retry and ambiguous-response tests |
| 30 cases / 40 retrieval queries / 10 unknown questions | Synthetic evaluation data + runner | Fixture harness executed; **not LLM accuracy evidence** |
| Single / multi / no-retrieval ablation | Yes | Fixture execution proven; live model comparison pending |
| Tokens / latency / cost | Usage trace + explicit-price calculation | Cost remains `null` without supplied prices/usage; no invented $ figure |
| Docker / CI | Definitions included | Docker unavailable here; workflows not remotely executed |

**No claim that multiple agents improve accuracy. No claim that citation existence proves entailment.**

## Quick start: zero-cost synthetic demo

From this directory (Python 3.11+, Node 22):

```bash
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
npm ci --prefix ui
npm run build --prefix ui
python -m uvicorn audit_copilot.app:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log
```

Open the service URL. In demo mode enter token **`demo`**, leave cycle **`demo-cycle`** and item **`demo-item`**, then investigate. Inspect the evidence and clauses, write a review note, then approve or reject. All changes affect only synthetic state, never AssetFlow. The fixture model deliberately makes a fixed demonstration proposal; **its outputs are not intelligent findings**.

The browser uses relative URLs. The demo contains no external fonts/CDNs, no API key input and no stored bearer token.

## Connect to a local/staging AssetFlow

1. Review the companion changes in `backend/src/audits/`, Prisma schema/migration, and `src/components/dashboard/AuditCopilotPanel.tsx`. Back up/configure the target according to AssetFlow's normal deployment process. Apply the migration only to an explicitly approved development/staging DB. This implementation does not authorize production changes.
2. Use an existing **ADMIN or ASSET_MANAGER** account. Signup still creates EMPLOYEE; promotion is a separate authorized step. No copilot service admin account is created.
3. Provision a **dedicated local** PostgreSQL+pgvector database for policy chunks (not AssetFlow's production database). Apply `schema.sql` there. The Compose file can create local services with `COPILOT_DB_PASSWORD` supplied privately; do not run `down -v` on existing data.
4. Configure `COPILOT_MODE=live`, the fixed `ASSETFLOW_URL` ending `/api`, `COPILOT_DATABASE_URL`, and provider keys privately from `.env.example`. `uvicorn --env-file .env ...` loads that file; the library itself does not automatically load it. Never put keys in Vite variables or send them in chat. Remote AssetFlow URLs require HTTPS; localhost and the explicit local Docker bridge are development exceptions.
5. Replace the authored demo corpus with reviewed organizational clauses, retaining stable IDs/source/version. Ingest only when API costs and data egress are approved:
   ```bash
   python -m audit_copilot.ingest --allow-paid-embeddings
   ```
6. Start the service. The standalone UI accepts the user's existing AssetFlow JWT in memory; the integrated panel reuses AssetFlow's session without manual copying.
7. To use the integrated panel, set **`VITE_COPILOT_ENABLED=true`** for an explicitly approved frontend build. Vite already proxies `/copilot-api` to local port 8000. For a deployed frontend add an equivalent **same-origin** proxy to the private copilot service, preserving Authorization, stripping only `/copilot-api`, and allowing a bounded ~100s upstream timeout. No deployment/proxy changes are applied automatically. Default feature flag is off.
8. Open an **open** audit cycle's items. The opt-in panel is shown only for managers. Clicking investigate may incur model charges; nothing runs automatically when an audit opens. Read all sources, then explicitly approve/reject with a note.

A production rollout additionally needs reviewed policies, live-provider acceptance, access/proxy configuration, retention/encryption, application-level budgets and operational review. Do not expose this MVP as a public multi-tenant SaaS.

## Testing

```bash
python -m pytest -q
python -m audit_copilot.evaluate --mode fixture
```

`artifacts/evaluation.json` includes per-class precision/recall/F1, confusion matrices, citation existence/relevance metrics, retrieval recall@5, refusal outcomes, per-variant latency and traces. It is visibly labelled **ENGINEERING FIXTURE HARNESS ONLY; NOT MODEL QUALITY**. The fixed demo model performs poorly on the gold set by design; the runner does not turn that into a positive model claim. Do not quote those scores as RAG/LLM quality.

### Full integration: actual AssetFlow + actual pgvector + official MCP

With the companion AssetFlow changes present:

```bash
# AssetFlow checkout:
npm ci --prefix backend
npm run prisma:generate --prefix backend
npm run build --prefix backend
# Copilot checkout:
npm ci --prefix integration
ASSETFLOW_ROOT=/absolute/path/to/assetflow COPILOT_PYTHON="$(command -v python)" npm test --prefix integration
```

The runner starts an ephemeral **in-memory PostgreSQL-WASM** instance, loads the actual AssetFlow SQL migrations and the pgvector extension, boots the real Nest API, signs up then promotes a synthetic user only inside that disposable DB, and runs the Python service through official MCP. It verifies investigation → source validation → human write → retry → exactly one receipt and activity event. Finally closes all local test processes/connections. No existing database URL or production credential is used.

Fixtures replace only the external LLM/embedding APIs in this integration test, not AssetFlow, MCP, SQL retrieval or approval persistence. This does not prove native production PostgreSQL performance or distributed concurrency.

### Live model evaluation (not executed here)

Configure the dedicated policy DB, ingest with live embeddings, review the synthetic labels, and explicitly authorize costs before:

```bash
python -m audit_copilot.evaluate --mode live --allow-paid-llm --limit 1
# Remove --limit only after validating one case and your budget.
```

The evaluation uses synthetic tool records and the configured live LLM/retriever. It does NOT write to AssetFlow. Live app integration with real evidence remains a separate acceptance check. Raw prompts/outputs may contain private data; evaluation fixtures here are synthetic, but your replacements need access/retention controls.

## Architecture

```
User JWT → AssetFlow /auth/me → scoped MCP read tools → Evidence agent
Authored/reviewed policies → PostgreSQL FTS + pgvector → Policy agent
                         structured reports ↓
                    Adjudicator (no tools/retrieval)
                               ↓
                 provenance validation + proposal journal
                               ↓ explicit human note
                    stale-context check + receipt key
                               ↓
        AssetFlow atomic mark + provenance receipt + activity event
```

- Evidence agent has six allowlisted reads and no retriever. Its bounded plan branches on asset state.
- Policy agent has retrieval but no AssetFlow/MCP access.
- Adjudicator receives reports only; there are no write tools exposed to any model.
- Separation is by interfaces/capabilities, **not OS/container sandboxing between agents**.
- Every cited quote must occur in fetched evidence/retrieved clauses. This prevents fabricated source IDs/quotes, not unsupported interpretations of real text.
- Existing observations are not automatically converted to VERIFIED because a transfer exists.

See [security and limitations](docs/SECURITY.md), [API contract](docs/API.md), and [executed verification](docs/VERIFICATION.md).
