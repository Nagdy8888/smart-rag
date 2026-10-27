-- Expand existing feedback catalog; preserve the seven-argument API.
-- Thumbs-up catalog plus 7-arg submit_run_feedback (tag required).
-- Expand-only. Keeps the ten unmerged diagnostic tags.

ALTER TABLE app.user_feedback
  DROP CONSTRAINT IF EXISTS user_feedback_tag_allowed;
ALTER TABLE app.user_feedback
  ADD CONSTRAINT user_feedback_tag_allowed
  CHECK (
    tag IS NULL
    OR tag IN (
      'helpful answer',
      'accurate citation',
      'correct route',
      'correct calculation',
      'sufficient graph',
      'chunk/cleaning loss',
      'profile field wrong',
      'candidate miss',
      'wrong rerank',
      'bad refusal/overconfident answer',
      'missed relationship',
      'wrong route',
      'wrong calculation',
      'bad citation',
      'insufficient graph',
      'incorrect answer', 'outdated answer', 'incomplete answer', 'wrong source'
    )
  );



CREATE OR REPLACE FUNCTION app.submit_run_feedback(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_rating smallint,
  p_comment text,
  p_tag text
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'feedback:authorization_rejected';
  END IF;

  IF p_rating IS NULL OR p_rating NOT IN (1, 5) THEN
    RAISE EXCEPTION 'feedback:invalid_rating';
  END IF;

  IF p_tag IS NULL OR p_tag NOT IN (
    'helpful answer',
    'accurate citation',
    'correct route',
    'correct calculation',
    'sufficient graph',
    'chunk/cleaning loss',
    'profile field wrong',
    'candidate miss',
    'wrong rerank',
    'bad refusal/overconfident answer',
    'missed relationship',
    'wrong route',
    'wrong calculation',
    'bad citation',
    'insufficient graph',
      'incorrect answer', 'outdated answer', 'incomplete answer', 'wrong source'
  ) THEN
    RAISE EXCEPTION 'feedback:invalid_tag';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'feedback:not_found';
  END IF;

  INSERT INTO app.user_feedback (run_id, user_id, rating, comment, tag)
  VALUES (
    p_run_id,
    caller_user_id,
    p_rating,
    CASE
      WHEN p_comment IS NULL OR btrim(p_comment) = '' THEN NULL
      ELSE left(p_comment, 2000)
    END,
    p_tag
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text, text
) IS
  'Creator-only thumbs feedback with a required unmerged polarity tag.';

REVOKE ALL ON FUNCTION app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text, text
) TO app_api;
