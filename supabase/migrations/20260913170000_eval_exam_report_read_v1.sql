-- P06-32: split-isolated latest report and count-only report-case listing.
-- Additive RPCs only. No table DML for runtime roles. Holdout rejected.

CREATE OR REPLACE FUNCTION app.get_latest_eval_exam_report_for_split(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_split text
)
RETURNS TABLE (
  exam_run_id uuid,
  split text,
  dataset_hash text,
  case_count integer,
  hit_count integer,
  hybrid_recall_at_10 numeric,
  gates_pass boolean,
  holdout_opened boolean,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_split text;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  v_split := lower(btrim(p_split));
  IF v_split = 'holdout' THEN
    RAISE EXCEPTION 'eval_exam:holdout_rejected';
  END IF;
  IF v_split NOT IN ('development', 'qualification') THEN
    RAISE EXCEPTION 'eval_exam:split_invalid';
  END IF;
  RETURN QUERY
  SELECT
    r.exam_run_id,
    r.split,
    r.dataset_hash,
    r.case_count,
    r.hit_count,
    r.hybrid_recall_at_10,
    r.gates_pass,
    r.holdout_opened,
    r.created_at
  FROM app.eval_exam_reports AS r
  INNER JOIN app.eval_exam_runs AS e ON e.id = r.exam_run_id
  WHERE e.status = 'succeeded'
    AND r.split = v_split
  ORDER BY r.created_at DESC, r.exam_run_id DESC
  LIMIT 1;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.list_eval_exam_report_cases(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid
)
RETURNS TABLE (
  exam_run_id uuid,
  case_id uuid,
  ordinal integer,
  hit boolean,
  gold_count integer,
  ranked_hit_count integer,
  latency_ms integer
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  IF NOT EXISTS (
    SELECT 1
    FROM app.eval_exam_reports AS r
    WHERE r.exam_run_id = p_exam_run_id
  ) THEN
    RETURN;
  END IF;
  RETURN QUERY
  SELECT
    c.exam_run_id,
    c.case_id,
    c.ordinal,
    c.hit,
    c.gold_count,
    c.ranked_hit_count,
    c.latency_ms
  FROM app.eval_exam_case_results AS c
  WHERE c.exam_run_id = p_exam_run_id
  ORDER BY c.ordinal ASC, c.case_id ASC;
END;
$fn$;

REVOKE ALL ON FUNCTION app.get_latest_eval_exam_report_for_split(
  uuid, text, bigint, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_latest_eval_exam_report_for_split(
  uuid, text, bigint, text
) TO app_api;

REVOKE ALL ON FUNCTION app.list_eval_exam_report_cases(
  uuid, text, bigint, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_eval_exam_report_cases(
  uuid, text, bigint, uuid
) TO app_api;

COMMENT ON FUNCTION app.get_latest_eval_exam_report_for_split(
  uuid, text, bigint, text
) IS
  'Latest succeeded count-only report for one split. Holdout rejected.';

COMMENT ON FUNCTION app.list_eval_exam_report_cases(
  uuid, text, bigint, uuid
) IS
  'Count-only case rows for a succeeded report. Missing report returns no rows.';
