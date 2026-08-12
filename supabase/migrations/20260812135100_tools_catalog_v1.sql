-- Phase 2 Packet 2: optional tool catalog, versions, permissions, usage events.

CREATE TABLE app.tool_catalog (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_key text NOT NULL,
  display_name text NOT NULL,
  description text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT tool_catalog_key_nonempty CHECK (btrim(tool_key) <> '')
);

CREATE UNIQUE INDEX tool_catalog_tool_key_uq
  ON app.tool_catalog (tool_key);

CREATE TABLE app.tool_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id uuid NOT NULL REFERENCES app.tool_catalog (id) ON DELETE CASCADE,
  version_label text NOT NULL,
  schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT tool_versions_unique_label UNIQUE (tool_id, version_label)
);

CREATE TABLE app.tool_permissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id uuid NOT NULL REFERENCES app.tool_catalog (id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users (id) ON DELETE CASCADE,
  role app.user_role,
  permission app.tool_permission_level NOT NULL DEFAULT 'none',
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT tool_permissions_target_present CHECK (
    user_id IS NOT NULL OR role IS NOT NULL
  )
);

CREATE TABLE app.tool_usage_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id uuid NOT NULL REFERENCES app.tool_catalog (id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL,
  event_kind text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TRIGGER tool_catalog_touch_updated_at
  BEFORE UPDATE ON app.tool_catalog
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER tool_permissions_touch_updated_at
  BEFORE UPDATE ON app.tool_permissions
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
