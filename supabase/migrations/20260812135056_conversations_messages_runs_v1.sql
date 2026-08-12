-- Phase 2 Packet 2: conversations, messages, runs, citations, feedback.

CREATE TABLE app.conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  creator_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  title text,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.conversations IS
  'Creator-private chat threads. Owner/admin audit access arrives in Packet 3 RLS.';

CREATE TABLE app.messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES app.conversations (id) ON DELETE CASCADE,
  role text NOT NULL,
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT messages_role_allowed CHECK (role IN ('user', 'assistant', 'system', 'tool'))
);

CREATE TABLE app.runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES app.conversations (id) ON DELETE CASCADE,
  creator_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  status app.run_status NOT NULL DEFAULT 'pending',
  graph_name text,
  idempotency_key text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE UNIQUE INDEX runs_idempotency_key_uq
  ON app.runs (idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE app.citations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  message_id uuid REFERENCES app.messages (id) ON DELETE SET NULL,
  chunk_id uuid REFERENCES app.document_chunks (id) ON DELETE SET NULL,
  citation_index integer NOT NULL,
  snippet text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT citations_index_nonnegative CHECK (citation_index >= 0)
);

CREATE TABLE app.user_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  rating smallint,
  comment text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT user_feedback_rating_range CHECK (
    rating IS NULL OR (rating >= 1 AND rating <= 5)
  )
);

CREATE TRIGGER conversations_touch_updated_at
  BEFORE UPDATE ON app.conversations
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER runs_touch_updated_at
  BEFORE UPDATE ON app.runs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
