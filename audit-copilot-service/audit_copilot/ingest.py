"""Explicit paid embedding ingestion into the dedicated copilot DB."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from .config import Settings
from .models import Clause
from .retrieval import CORPUS, OpenAIEmbedder, PgRetrieval


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=CORPUS)
    p.add_argument("--allow-paid-embeddings", action="store_true")
    args = p.parse_args()
    if not args.allow_paid_embeddings:
        p.error(
            "Ingestion calls the embedding API; explicit --allow-paid-embeddings is required"
        )
    s = Settings.env()
    if not s.database_url:
        p.error("COPILOT_DATABASE_URL required")
    clauses = [Clause(**x) for x in json.loads(args.corpus.read_text())]
    if len({c.id for c in clauses}) != len(clauses):
        p.error("Duplicate clause IDs")
    r = PgRetrieval(
        s.database_url,
        OpenAIEmbedder(
            os.getenv("OPENAI_API_KEY", ""), s.embedding_model, s.embedding_dim
        ),
    )
    asyncio.run(r.ingest(clauses))
    print(
        f"Ingested {len(clauses)} clauses. Authored demo policies are not real organizational rules."
    )


if __name__ == "__main__":
    main()
