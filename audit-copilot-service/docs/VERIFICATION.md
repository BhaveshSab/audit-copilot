# Executed verification and remaining acceptance

## Scope

Local source implementation on AssetFlow branch `arena/595baf83-assetflow`, checkout base `e3b214055c58d14f7daec678dbcfa1393bef397e`. The current checkout had pre-existing infrastructure modifications; those were not reset or included in the copilot integration package. The separately named Audit Copilot GitHub repository was empty when inspected. **No code was pushed there or to the AssetFlow remote by this implementation turn.**

“Phases 2–5” are the copilot retrieval, orchestration, human review and evaluation phases—not the earlier capacity-test stages. All four have code and fixture/integration coverage. This is **not** a claim that live LLM quality or a production rollout has passed.

## Results actually executed

| Check | Result | What it proves |
|---|---|---|
| Python safety/HTTP/MCP/provider-contract/evaluation tests | **29 passed** | Auth, scope, source provenance, refusal schema, budgets, failure paths, human review/retry and fixture runner |
| AssetFlow frontend suite | **112 passed, 18 files** | Existing frontend regression suite plus 3 new copilot-panel tests |
| AssetFlow backend unit suite | **123 passed, 18 suites** | Existing backend unit regressions |
| AssetFlow backend E2E suite, final run | **203 passed, 7 skipped, 22 suites passed** | Real Nest API, PostgreSQL-WASM migrations, existing workflows and new human decision contract |
| New copilot decision E2E coverage | **7 cases** (included above) | Atomic mark/receipt/activity/notification; retry; rollback; stale/closed/denied/wrong-item rejection |
| Cross-service acceptance | **PASS** | Real AssetFlow HTTP + official MCP subprocess + real PostgreSQL FTS and pgvector + stored proposal + human apply + repeat receipt |
| Actual six MCP tools against real API | **PASS** | Fixed route mappings, delegated bearer, cycle/item binding; wrong item denied |
| Backend build | **PASS** | Nest/TypeScript build |
| AssetFlow frontend build | **PASS** | TypeScript + Vite integration build |
| Standalone review UI build | **PASS** | React/Vite production bundle |
| Python Ruff checks / compile | **PASS** | Static checks, import/syntax validation |
| Fixture evaluation run | **30 cases × 3 variants, 40 queries, 10 refusal questions** | Evaluation plumbing; not model-quality evidence |
| Live preview HTTP smoke | **PASS** | Index 200, demo health, investigation 201, AWAITING_REVIEW |
| Whitespace diff check | **PASS** | No Git whitespace errors |

Seven existing E2E tests were skipped because the optional live S3 bucket and Redis queue test services were not configured. They are not copilot feature passes. Existing pg-driver deprecation and React Router future-flag warnings remain. The rollback test deliberately emits a synthetic server-error log and then proves no mutation/receipt survived.

### Reproduction commands

From AssetFlow root with local Python environment installed:

```bash
.venv/bin/python -m pytest audit-copilot/tests -q
npm test -- --run
npm run test:unit --prefix backend -- --runInBand --silent
npm run test:e2e --prefix backend -- --runInBand --silent
npm run build --prefix backend
npm run build
npm run build --prefix audit-copilot/ui
npm test --prefix audit-copilot/integration
cd audit-copilot && ../.venv/bin/python -m audit_copilot.evaluate
```

The initial Prisma generation command could not download native engines from `binaries.prisma.sh` under this sandbox's network restrictions. For **client generation only**, the Rust-free `engineType=client` schema was generated with unused native-engine paths explicitly set to `/bin/false`; it completed successfully. No native migration command is claimed to have run. All SQL migrations were actually replayed by the disposable PostgreSQL-WASM test database, through the real Prisma PG adapter. On a normal allowed development machine use ordinary `npm run prisma:generate`.

## What is NOT verified

- Live OpenAI/Gemini generation, paid semantic embeddings, provider availability or invoice-level costs. External provider API hosts are outside this sandbox's network allowlist; no user keys were requested or read.
- Model finding precision/recall/F1, calibrated refusal performance, real semantic retrieval recall, or multi-agent advantage.
- Real organizational policy authority or independently reviewed evaluation labels. The 60 clauses and cases are authored synthetic data.
- Docker image/Compose execution: Docker is not installed in this workspace. Definitions are supplied, not called proven.
- Remote GitHub Actions success for the new workflow. CI files were written but no push/run was performed.
- Browser automation in a real browser engine. Review panel interactions were tested in jsdom; preview HTTP and production builds were tested.
- Production deployment, production DB migration, actual user pilot, distributed concurrency/load, hard dollar spend caps or multi-tenancy.
- Telegram approvals, automatic cycle-open execution, PDF/OCR ingestion, or learned cross-encoder reranking. These are explicitly outside this version.

## Fixture evaluation interpretation

The demo model intentionally returns a fixed reviewable transfer-investigation proposal, or refuses when no policy context exists. It is a UI/integration fixture, not a trained classifier. Consequently, fixture evaluation does **not** demonstrate useful accuracy or refusal quality. Poor fixture scores are retained, not hidden. Its first full run classified only 4/30 cases correctly in the single/multi variants and refused none of the 10 unknown questions. **Do not put these on a resume as model performance.** The no-retrieval variant refuses because the same citation safety remains enforced.

Use the runner with explicitly approved live APIs and reviewed labels to obtain actual model results. Publish the actual comparison even if single-agent performs better. Citation existence precision must not be relabelled as factual correctness.

## Resume claims supported now

You may describe the implemented architecture and executed test counts, carefully scoped to this local implementation. Do not claim live LLM quality, production deployment, guaranteed hallucination prevention, a semantic retrieval score or a measured multi-agent improvement.

## Next acceptance gates

1. Transfer the standalone service into the requested repository in a session attached to that repository; review/apply the companion AssetFlow patch against its actual current checkout, without resetting unrelated changes.
2. Review real policies and labels; configure a dedicated non-production pgvector database and private provider credentials outside chat.
3. Explicitly approve a small paid embedding/generation smoke (`--limit 1` limits each evaluation set), inspect traces, then run the full labelled evaluation within a chosen budget.
4. Validate live review against staging AssetFlow, and separately review proxy, retention/encryption and deployment controls before production.
