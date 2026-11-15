-- Dedicated copilot database. Never run against production without review.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS copilot_clause (
  id text PRIMARY KEY,
  title text NOT NULL,
  body text NOT NULL,
  source text NOT NULL,
  version text NOT NULL,
  embedding_model text NOT NULL,
  embedding vector(1536) NOT NULL,
  search tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED
);
CREATE INDEX IF NOT EXISTS copilot_clause_search ON copilot_clause USING gin(search);
CREATE INDEX IF NOT EXISTS copilot_clause_embedding ON copilot_clause USING hnsw(embedding vector_cosine_ops);
