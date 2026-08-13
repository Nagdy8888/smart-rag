-- ParadeDB bootstrap: enable pg_search (and required vector) plus least-privilege roles.
-- Application BM25 projection DDL remains Phase 2/4-owned.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paradedb_writer') THEN
    CREATE ROLE paradedb_writer LOGIN PASSWORD 'change-me-paradedb-writer';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paradedb_reader') THEN
    CREATE ROLE paradedb_reader LOGIN PASSWORD 'change-me-paradedb-reader';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE paradedb TO paradedb_writer, paradedb_reader;
GRANT USAGE ON SCHEMA public TO paradedb_writer, paradedb_reader;
ALTER ROLE paradedb_writer SET search_path = public;
ALTER ROLE paradedb_reader SET search_path = public;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO paradedb_reader;
