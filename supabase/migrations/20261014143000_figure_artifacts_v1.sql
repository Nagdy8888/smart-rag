-- Private figure PNGs and their descriptions. Public URLs are not used.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('figure-artifacts', 'figure-artifacts', false, 1500000, ARRAY['image/png']::text[])
ON CONFLICT (id) DO UPDATE
SET public = false,
    name = EXCLUDED.name,
    file_size_limit = EXCLUDED.file_size_limit;

CREATE TABLE app.document_figures (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  figure_key text NOT NULL,
  page_index integer NOT NULL,
  storage_bucket text NOT NULL,
  storage_path text NOT NULL,
  content_hash text NOT NULL,
  byte_size integer NOT NULL,
  caption text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  model_id text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT document_figures_page_nonnegative CHECK (page_index >= 0),
  CONSTRAINT document_figures_bytes_positive CHECK (byte_size > 0),
  CONSTRAINT document_figures_unique_key UNIQUE (version_id, figure_key)
);

COMMENT ON TABLE app.document_figures IS
  'ACL-scoped figure PNG metadata. Pixel bytes live in figure-artifacts.';

ALTER TABLE app.document_figures ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON app.document_figures TO app_worker;
GRANT SELECT ON app.document_figures TO app_api;

DROP POLICY IF EXISTS document_figures_worker_rw ON app.document_figures;
CREATE POLICY document_figures_worker_rw
  ON app.document_figures
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS document_figures_api_read ON app.document_figures;
CREATE POLICY document_figures_api_read
  ON app.document_figures
  FOR SELECT
  TO app_api
  USING (true);
