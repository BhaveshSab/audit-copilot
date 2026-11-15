"""Demo lexical/hash retrieval and live PostgreSQL FTS + pgvector RRF.
Postgres ts_rank_cd is NOT BM25. The local hash embedder is NOT semantic AI.
"""

import hashlib
import json
import math
import re
from pathlib import Path

import httpx

from .models import Clause

CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "policies.json"


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", text.lower())


def local_vector(text, dim=64):
    v = [0.0] * dim
    for t in tokens(text):
        v[int(hashlib.sha256(t.encode()).hexdigest(), 16) % dim] += 1
    n = math.sqrt(sum(x * x for x in v)) or 1
    return [x / n for x in v]


def rrf(lexical, vector, limit=5):
    scores = {}
    for order in (lexical, vector):
        for rank, cid in enumerate(order, 1):
            scores[cid] = scores.get(cid, 0) + 1 / (60 + rank)
    return sorted(scores, key=lambda x: (-scores[x], x))[:limit]


class DemoRetrieval:
    def __init__(self, clauses=None):
        self.clauses = {
            c.id: c
            for c in (
                clauses
                if clauses is not None
                else [Clause(**x) for x in json.loads(CORPUS.read_text())]
            )
        }

    async def search(self, query, limit=5):
        qt = set(tokens(query))
        qv = local_vector(query)
        lexical = sorted(
            self.clauses,
            key=lambda k: (
                -len(
                    qt & set(tokens(self.clauses[k].title + " " + self.clauses[k].text))
                ),
                k,
            ),
        )
        # No overlap => retrieval abstains, rather than always returning a chunk.
        lexical = [
            k
            for k in lexical
            if qt & set(tokens(self.clauses[k].title + " " + self.clauses[k].text))
        ][:20]
        vector = sorted(
            lexical,
            key=lambda k: (
                -sum(
                    a * b
                    for a, b in zip(qv, local_vector(self.clauses[k].text), strict=True)
                )
            ),
        )
        return [self.clauses[k] for k in rrf(lexical, vector, limit)]


class OpenAIEmbedder:
    def __init__(self, key, model="text-embedding-3-small", dim=1536):
        if not key:
            raise ValueError("OPENAI_API_KEY required for live semantic embeddings")
        self.key, self.model, self.dim = key, model, dim

    async def embed(self, texts):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "dimensions": self.dim, "input": texts},
            )
            r.raise_for_status()
            rows = sorted(r.json()["data"], key=lambda x: x["index"])
            if len(rows) != len(texts):
                raise ValueError("Embedding count mismatch")
            vectors = [x["embedding"] for x in rows]
            if any(
                len(v) != self.dim or not all(math.isfinite(x) for x in v)
                for v in vectors
            ):
                raise ValueError("Invalid embedding")
            return vectors


class PgRetrieval:
    def __init__(self, dsn, embedder):
        self.dsn, self.embedder = dsn, embedder

    async def ingest(self, clauses):
        import psycopg

        vectors = await self.embedder.embed([c.title + " " + c.text for c in clauses])
        async with await psycopg.AsyncConnection.connect(self.dsn) as db:
            for c, v in zip(clauses, vectors, strict=True):
                await db.execute(
                    """INSERT INTO copilot_clause(id,title,body,source,version,embedding_model,embedding)
                  VALUES(%s,%s,%s,%s,%s,%s,%s::vector)
                  ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,source=excluded.source,
                  version=excluded.version,embedding_model=excluded.embedding_model,embedding=excluded.embedding""",
                    (
                        c.id,
                        c.title,
                        c.text,
                        c.source,
                        c.version,
                        self.embedder.model,
                        json.dumps(v),
                    ),
                )

    async def search(self, query, limit=5):
        import psycopg
        from psycopg.rows import dict_row

        v = (await self.embedder.embed([query]))[0]
        async with await psycopg.AsyncConnection.connect(
            self.dsn, row_factory=dict_row
        ) as db:
            # Both lists are scoped to the configured embedding model.
            lex = await (
                await db.execute(
                    """SELECT id FROM copilot_clause
                WHERE embedding_model=%s AND search @@ plainto_tsquery('english',%s)
                ORDER BY ts_rank_cd(search,plainto_tsquery('english',%s)) DESC,id LIMIT 20""",
                    (self.embedder.model, query, query),
                )
            ).fetchall()
            vec = await (
                await db.execute(
                    """SELECT id FROM copilot_clause WHERE embedding_model=%s
                ORDER BY embedding <=> %s::vector,id LIMIT 20""",
                    (self.embedder.model, json.dumps(v)),
                )
            ).fetchall()
            ids = rrf([x["id"] for x in lex], [x["id"] for x in vec], limit)
            if not ids:
                return []
            rows = await (
                await db.execute(
                    "SELECT id,title,body AS text,source,version FROM copilot_clause WHERE id=ANY(%s)",
                    (ids,),
                )
            ).fetchall()
            byid = {r["id"]: Clause(**r) for r in rows}
            return [byid[k] for k in ids]
