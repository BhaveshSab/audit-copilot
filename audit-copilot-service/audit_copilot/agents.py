import asyncio
import json

from .models import Evidence, EvidenceReport, Fact, Finding, PolicyRef, PolicyReport


class EvidenceAgent:
    """Has read-only MCP gateway, NO retriever. Branches on actual asset state."""

    def __init__(self, gateway, llm):
        self.gateway, self.llm = gateway, llm

    async def run(self, args):
        evidence = []

        async def read(tool):
            data = await self.gateway.tool(tool, args)
            e = Evidence(id=f"E{len(evidence) + 1}", tool=tool, data=data)
            evidence.append(e)
            return data

        await read("get_audit_item")
        asset = await read("get_asset")
        # Explicit bounded plan. No model-supplied arbitrary URLs/tools.
        await read("get_allocation_history")
        if asset.get("status") == "ALLOCATED":
            await read("get_transfers")
        if (
            asset.get("status") == "UNDER_MAINTENANCE"
            or asset.get("condition") == "DAMAGED"
        ):
            await read("get_maintenance_history")
        await read("get_activity")
        report = await self.llm.generate(
            "Evidence agent: extract only verbatim source facts",
            [e.model_dump() for e in evidence],
            EvidenceReport,
        )
        byid = {e.id: json.dumps(e.data, sort_keys=True) for e in evidence}
        for f in report.facts:
            if f.evidence_id not in byid or f.quote not in byid[f.evidence_id]:
                raise ValueError("Evidence quote is not in fetched record")
        return evidence, report


class PolicyAgent:
    """Has retrieval, NO AssetFlow/MCP tool gateway."""

    def __init__(self, retrieval, llm):
        self.retrieval, self.llm = retrieval, llm

    async def run(self, query):
        clauses = await self.retrieval.search(query)
        report = await self.llm.generate(
            "Policy agent: select governing clauses; do not infer asset facts",
            [c.model_dump() for c in clauses],
            PolicyReport,
        )
        byid = {c.id: c for c in clauses}
        for ref in report.refs:
            if ref.clause_id not in byid or ref.quote not in byid[ref.clause_id].text:
                raise ValueError("Policy quote is not in retrieved clause")
        return clauses, report


class Adjudicator:
    """NO tools, NO retrieval. Structured reports are its only inputs."""

    def __init__(self, llm):
        self.llm = llm

    async def run(self, evidence, policy):
        finding = await self.llm.generate(
            "Adjudicator: propose a finding or refuse; never apply it",
            {
                "evidence_report": evidence.model_dump(),
                "policy_report": policy.model_dump(),
            },
            Finding,
        )
        known_e = {x.evidence_id for x in evidence.facts}
        known_p = {(x.clause_id, x.quote) for x in policy.refs}
        if not set(finding.evidence_ids) <= known_e:
            raise ValueError("Unfetched evidence citation")
        if any((r.clause_id, r.quote) not in known_p for r in finding.policy_refs):
            raise ValueError("Unretrieved policy citation")
        return finding


async def investigate(args, gateway, retrieval, llm, seconds=90):
    states = ["CREATED", "COLLECTING"]
    async with asyncio.timeout(seconds):
        # Same budget used by both agents; adjudicator cannot invoke their tools.
        (evidence, er), (clauses, pr) = await asyncio.gather(
            EvidenceAgent(gateway, llm).run(args),
            PolicyAgent(retrieval, llm).run(args.question),
        )
        states.append("ADJUDICATING")
        finding = await Adjudicator(llm).run(er, pr)
        states.append("REFUSED" if finding.refused else "AWAITING_REVIEW")
        return {
            "states": states,
            "finding": finding.model_dump(),
            "evidence": [e.model_dump() for e in evidence],
            "clauses": [c.model_dump() for c in clauses],
            "evidence_report": er.model_dump(),
            "policy_report": pr.model_dump(),
        }


class FixtureLLM:
    """Deterministic demo ONLY. Never a claim of LLM quality/cost/latency."""

    async def generate(self, role, payload, schema):
        if schema is EvidenceReport:
            return EvidenceReport(
                facts=[
                    Fact(
                        evidence_id=e["id"],
                        quote=json.dumps(e["data"], sort_keys=True)[:1800],
                    )
                    for e in payload
                ],
                summary="Synthetic record excerpts; human investigation required.",
            )
        if schema is PolicyReport:
            return PolicyReport(
                refs=[
                    PolicyRef(clause_id=c["id"], quote=c["text"]) for c in payload[:2]
                ],
                summary="Authored demonstration policies, not organizational authority.",
            )
        er, pr = payload["evidence_report"], payload["policy_report"]
        if not pr["refs"] or not er["facts"]:
            return Finding(
                category="insufficient_evidence",
                result=None,
                cause="No grounded context.",
                evidence_ids=[],
                policy_refs=[],
                confidence=0,
                recommended_action="Ask a human auditor.",
                refused=True,
            )
        return Finding(
            category="transferred",
            result="MISSING",
            cause="SYNTHETIC DEMO: transfer history warrants human investigation; preserve the existing MISSING observation.",
            evidence_ids=[f["evidence_id"] for f in er["facts"]],
            policy_refs=pr["refs"],
            confidence=0.5,
            recommended_action="Contact the receiving custodian; do not infer physical presence from a transfer.",
            refused=False,
        )
