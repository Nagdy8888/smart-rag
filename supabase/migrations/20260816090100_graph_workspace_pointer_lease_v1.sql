-- Phase 5 Packet 2 precondition: application-owned workspace/pointer/lease/config.
-- Schema only. Packet 3 owns the writer. This is not Graph Ready.

DO $$
BEGIN
  CREATE TYPE app.graph_workspace_state AS ENUM (
    'building',
    'active',
    'updating',
    'filtered_dirty',
    'quarantined',
    'disabled',
    'retired'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

COMMENT ON TYPE app.graph_workspace_state IS
  'LightRAG workspace lifecycle. Packet 2 schema only; Packet 3 owns transitions.';

CREATE TABLE IF NOT EXISTS app.graph_workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_key text NOT NULL,
  state app.graph_workspace_state NOT NULL,
  embedding_model text NOT NULL DEFAULT 'text-embedding-3-large',
  embedding_dimensions integer NOT NULL DEFAULT 1024,
  schema_fingerprint jsonb NOT NULL DEFAULT '{}'::jsonb,
  config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_workspaces_key_nonempty CHECK (btrim(workspace_key) <> ''),
  CONSTRAINT graph_workspaces_embedding_model_pin
    CHECK (embedding_model = 'text-embedding-3-large'),
  CONSTRAINT graph_workspaces_embedding_dimensions_pin
    CHECK (embedding_dimensions = 1024)
);

CREATE UNIQUE INDEX IF NOT EXISTS graph_workspaces_workspace_key_uq
  ON app.graph_workspaces (workspace_key);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'graph_workspaces_touch_updated_at'
  ) THEN
    CREATE TRIGGER graph_workspaces_touch_updated_at
      BEFORE UPDATE ON app.graph_workspaces
      FOR EACH ROW
      EXECUTE FUNCTION app.touch_updated_at();
  END IF;
END
$$;

COMMENT ON TABLE app.graph_workspaces IS
  'Application-owned LightRAG workspace rows plus embedding/config snapshot. Not Graph Ready.';

CREATE TABLE IF NOT EXISTS app.graph_active_workspace_pointer (
  id uuid PRIMARY KEY,
  workspace_id uuid REFERENCES app.graph_workspaces (id),
  generation bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_active_workspace_pointer_singleton
    CHECK (id = '00000000-0000-0000-0000-000000000001'::uuid),
  CONSTRAINT graph_active_workspace_pointer_generation_positive
    CHECK (generation >= 1)
);

INSERT INTO app.graph_active_workspace_pointer (id, workspace_id, generation)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid, NULL, 1)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE app.graph_active_workspace_pointer IS
  'Singleton company active-workspace pointer. Packet 7 takes FOR UPDATE on generation.';

CREATE TABLE IF NOT EXISTS app.graph_writer_lease (
  id uuid PRIMARY KEY,
  owner text,
  token text,
  expires_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_writer_lease_singleton
    CHECK (id = '00000000-0000-0000-0000-000000000001'::uuid)
);

INSERT INTO app.graph_writer_lease (id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE app.graph_writer_lease IS
  'Singleton graph-writer lease schema. Packet 2 has no writer implementation.';

ALTER TABLE app.graph_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE app.graph_active_workspace_pointer ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_active_workspace_pointer FORCE ROW LEVEL SECURITY;
ALTER TABLE app.graph_writer_lease ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_writer_lease FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_workspaces'
      AND policyname = 'graph_workspaces_worker_rw'
  ) THEN
    CREATE POLICY graph_workspaces_worker_rw
      ON app.graph_workspaces
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_workspaces'
      AND policyname = 'graph_workspaces_api_select'
  ) THEN
    CREATE POLICY graph_workspaces_api_select
      ON app.graph_workspaces
      FOR SELECT
      TO app_api
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_active_workspace_pointer'
      AND policyname = 'graph_active_workspace_pointer_worker_rw'
  ) THEN
    CREATE POLICY graph_active_workspace_pointer_worker_rw
      ON app.graph_active_workspace_pointer
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_active_workspace_pointer'
      AND policyname = 'graph_active_workspace_pointer_api_select'
  ) THEN
    CREATE POLICY graph_active_workspace_pointer_api_select
      ON app.graph_active_workspace_pointer
      FOR SELECT
      TO app_api
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_writer_lease'
      AND policyname = 'graph_writer_lease_worker_rw'
  ) THEN
    CREATE POLICY graph_writer_lease_worker_rw
      ON app.graph_writer_lease
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON app.graph_workspaces TO app_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.graph_active_workspace_pointer TO app_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.graph_writer_lease TO app_worker;
GRANT SELECT ON app.graph_workspaces TO app_api;
GRANT SELECT ON app.graph_active_workspace_pointer TO app_api;

REVOKE ALL ON app.graph_workspaces FROM PUBLIC, anon, authenticated, app_lightrag;
REVOKE ALL ON app.graph_active_workspace_pointer FROM PUBLIC, anon, authenticated, app_lightrag;
REVOKE ALL ON app.graph_writer_lease FROM PUBLIC, anon, authenticated, app_lightrag, app_api;
