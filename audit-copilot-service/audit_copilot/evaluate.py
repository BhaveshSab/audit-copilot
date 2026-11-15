"""Evaluation runner. Fixture mode checks plumbing, NOT live LLM quality."""

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

from .agents import EvidenceAgent, FixtureLLM, investigate
from .assetflow import ScopeError
from .config import Settings
from .models import Finding, Investigate
from .providers import LLM
from .retrieval import DemoRetrieval, OpenAIEmbedder, PgRetrieval

ROOT = Path(__file__).resolve().parents[1]


class CaseGateway:
    def __init__(self, case):
        self.records = case["records"]

    async def tool(self, name, args):
        if name not in self.records:
            raise ScopeError("No fixture for requested tool")
        return self.records[name]


class EmptyRetrieval:
    async def search(self, query, limit=5):
        return []


def classification(gold, predictions):
    labels = sorted(set(gold) | set(predictions))
    matrix = {
        a: dict(Counter(p for g, p in zip(gold, predictions, strict=True) if g == a))
        for a in labels
    }
    per = {}
    for label in labels:
        tp = sum(g == p == label for g, p in zip(gold, predictions, strict=True))
        fp = sum(
            g != label and p == label for g, p in zip(gold, predictions, strict=True)
        )
        fn = sum(
            g == label and p != label for g, p in zip(gold, predictions, strict=True)
        )
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        per[label] = {
            "support": gold.count(label),
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall)
            if precision + recall
            else 0,
        }
    gold_labels = sorted(set(gold))
    return {
        "confusion_matrix": matrix,
        "per_class": per,
        "accuracy": sum(g == p for g, p in zip(gold, predictions, strict=True))
        / len(gold),
        "macro_f1": sum(per[k]["f1"] for k in gold_labels) / len(gold_labels),
        "false_findings_on_clean": sum(
            g == "clean" and p not in {"clean", "insufficient_evidence", "error"}
            for g, p in zip(gold, predictions, strict=True)
        ),
        "clean_abstentions_or_errors": sum(
            g == "clean" and p in {"insufficient_evidence", "error"}
            for g, p in zip(gold, predictions, strict=True)
        ),
    }


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


async def case_run(case, variant, retrieval, llm):
    args = Investigate(
        cycle_id="eval-cycle", item_id=case["id"], question=case["question"]
    )
    gateway = CaseGateway(case)
    if variant != "single":
        return await investigate(
            args,
            gateway,
            EmptyRetrieval() if variant == "multi_no_retrieval" else retrieval,
            llm,
        )
    evidence, er = await EvidenceAgent(gateway, FixtureLLM()).run(args)
    clauses = await retrieval.search(args.question)
    finding = await llm.generate(
        "Single agent baseline: investigate these records and clauses or refuse",
        {
            "records": [e.model_dump() for e in evidence],
            "clauses": [c.model_dump() for c in clauses],
            # Same structured report fields allow the fixture harness to run;
            # they are mechanical extracts, not separate model-agent decisions.
            "evidence_report": er.model_dump(),
            "policy_report": {
                "refs": [{"clause_id": c.id, "quote": c.text} for c in clauses],
                "summary": "Retrieved clauses",
            },
        },
        Finding,
    )
    known = {c.id: c.text for c in clauses}
    if not set(finding.evidence_ids) <= {e.id for e in evidence}:
        raise ValueError("Invalid single-agent evidence reference")
    if any(
        r.clause_id not in known or r.quote not in known[r.clause_id]
        for r in finding.policy_refs
    ):
        raise ValueError("Invalid single-agent policy reference")
    return {
        "finding": finding.model_dump(),
        "evidence": [e.model_dump() for e in evidence],
        "clauses": [c.model_dump() for c in clauses],
    }


async def evaluate(mode="fixture", limit=None):
    settings = Settings.env()
    retriever = (
        DemoRetrieval()
        if mode == "fixture"
        else PgRetrieval(
            settings.database_url,
            OpenAIEmbedder(
                os.environ.get("OPENAI_API_KEY", ""),
                settings.embedding_model,
                settings.embedding_dim,
            ),
        )
    )
    cases = json.loads((ROOT / "evals/cases.json").read_text())[:limit]
    queries = json.loads((ROOT / "evals/retrieval.json").read_text())[:limit]
    unknown = json.loads((ROOT / "evals/refusals.json").read_text())[:limit]
    retrieval_scores = []
    top_hits = []
    for q in queries:
        hits = await retriever.search(q["question"])
        ids = {c.id for c in hits}
        relevant = set(q["relevant"])
        retrieval_scores.append(len(ids & relevant) / len(relevant))
        top_hits.append(
            {
                "id": q["id"],
                "hits": sorted(ids),
                "recall_at_5": retrieval_scores[-1],
                "relevance_precision_at_5": len(ids & relevant) / len(ids)
                if ids
                else 0,
            }
        )
    variants = {}
    traces = []
    for variant in ("single", "multi", "multi_no_retrieval"):
        predicted = []
        durations = []
        usage = []
        errors = 0
        valid_cites = 0
        all_cites = 0
        relevant_cites = 0
        for case in cases:
            llm = FixtureLLM() if mode == "fixture" else LLM(settings)
            started = time.monotonic()
            try:
                result = await case_run(case, variant, retriever, llm)
                prediction = result["finding"]["category"]
                source = {c["id"]: c["text"] for c in result["clauses"]}
                for ref in result["finding"]["policy_refs"]:
                    all_cites += 1
                    valid_cites += int(
                        ref["clause_id"] in source
                        and ref["quote"] in source[ref["clause_id"]]
                    )
                    relevant_cites += int(ref["clause_id"] in case["relevant"])
                traces.append(
                    {"case": case["id"], "variant": variant, "result": result}
                )
            except Exception as e:
                prediction = "error"
                errors += 1
                traces.append(
                    {
                        "case": case["id"],
                        "variant": variant,
                        "error_type": type(e).__name__,
                    }
                )
            predicted.append(prediction)
            durations.append(time.monotonic() - started)
            usage.extend(getattr(getattr(llm, "budget", None), "usage", []))
        variants[variant] = {
            **classification([c["category"] for c in cases], predicted),
            "errors": errors,
            "citation_existence_precision": valid_cites / all_cites
            if all_cites
            else None,
            "labelled_citation_relevance_precision": relevant_cites / all_cites
            if all_cites
            else None,
            "p95_seconds": percentile(durations, 0.95),
            "usage": usage,
            "generation_cost_usd": sum(x["cost_usd"] for x in usage)
            if usage and all(x["cost_usd"] is not None for x in usage)
            else None,
            "total_cost_usd": None,  # Embedding billing is not supplied by the API.
        }
    refusals = []
    base = cases[0]
    for q in unknown:
        llm = FixtureLLM() if mode == "fixture" else LLM(settings)
        try:
            result = await case_run(
                {**base, "question": q["question"]}, "multi", retriever, llm
            )
            refusals.append(
                {"id": q["id"], "refused": result["finding"]["refused"], "error": False}
            )
        except Exception:
            refusals.append({"id": q["id"], "refused": False, "error": True})
    return {
        "mode": mode,
        "claim_scope": "ENGINEERING FIXTURE HARNESS ONLY; NOT MODEL QUALITY"
        if mode == "fixture"
        else "SYNTHETIC LABELLED EVALUATION; NOT REAL AUDITOR VALIDATION",
        "cases": len(cases),
        "queries": len(queries),
        "refusal_questions": len(unknown),
        "retrieval": {
            "mean_recall_at_5": sum(retrieval_scores) / len(retrieval_scores),
            "per_query": top_hits,
        },
        "variants": variants,
        "refusals": refusals,
        "refusal_rate": sum(x["refused"] for x in refusals) / len(refusals),
        "traces": traces,
        "limitations": [
            "Authored synthetic policy and gold labels need independent review.",
            "Fixture embeddings are hash vectors, not semantic embeddings.",
            "Citation existence does not prove entailment.",
            "No-retrieval ablation retains citation safety and may therefore refuse more often.",
            "No claim that multiple agents outperform a single agent.",
            "Prices are not inferred; unavailable USD cost is null.",
            "Generation cost excludes embeddings; total cost remains null without complete billing evidence.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    p.add_argument("--allow-paid-llm", action="store_true")
    p.add_argument("--output", default="artifacts/evaluation.json")
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    if args.mode == "live" and not args.allow_paid_llm:
        p.error(
            "Live evaluation requires explicit --allow-paid-llm and configured credentials; may incur charges"
        )
    if args.limit is not None and args.limit < 1:
        p.error("--limit must be positive")
    result = asyncio.run(evaluate(args.mode, args.limit))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("mode", "claim_scope", "cases", "queries", "refusal_rate")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
