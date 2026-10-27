-- Anonymous company aggregates; document and maintenance details retain ACL/consent.
CREATE FUNCTION app.admin_overview(caller_user_id uuid, caller_role text,
  caller_authorization_version bigint, p_days integer DEFAULT 30)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, app SET statement_timeout = '10s' AS $fn$
DECLARE snapshot_at timestamptz := statement_timestamp(); start_at timestamptz; result jsonb;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id,caller_role,caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  IF caller_role NOT IN ('owner','admin') THEN RAISE EXCEPTION 'documents:forbidden'; END IF;
  IF p_days NOT IN (7,30,90) OR p_days IS NULL THEN RAISE EXCEPTION 'overview:invalid_period'; END IF;
  start_at := (date_trunc('day', snapshot_at AT TIME ZONE 'UTC') - (p_days-1)*interval '1 day') AT TIME ZONE 'UTC';
  WITH query_runs AS MATERIALIZED (
    SELECT r.* FROM app.runs r JOIN app.conversations c ON c.id=r.conversation_id
    WHERE r.graph_name='query' AND c.deleted_at IS NULL
      AND r.created_at >= start_at AND r.created_at <= snapshot_at
  ), daily_runs AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day,count(*) AS questions FROM query_runs GROUP BY 1
  ), daily_cost AS (
    SELECT (recorded_at AT TIME ZONE 'UTC')::date AS day,sum(cost_usd) AS cost
    FROM app.llm_usage WHERE recorded_at >= start_at AND recorded_at <= snapshot_at GROUP BY 1
  ), outcomes AS (
    SELECT knowledge_result->>'outcome' AS outcome,count(*) AS n FROM query_runs
    WHERE status IN ('completed','partial') AND knowledge_result->>'outcome' IN ('supported','partial','insufficient_evidence','conflicting_evidence')
    GROUP BY 1
  ), visible_documents AS MATERIALIZED (
    SELECT d.id,d.title,d.knowledge_owner_user_id,d.review_due_at,v.authority_status
    FROM app.documents d LEFT JOIN app.document_versions v ON v.id=d.current_version_id AND v.document_id=d.id
    WHERE d.deleted_at IS NULL AND app.caller_can_read_document(caller_user_id,caller_role,d.id)
  ), candidates AS (
    SELECT 'missing_owner'::text AS kind,d.id AS source_id,d.id AS document_id,d.title,5 AS priority
    FROM visible_documents d WHERE d.knowledge_owner_user_id IS NULL
    UNION ALL SELECT 'overdue_review',d.id,d.id,d.title,4 FROM visible_documents d
      WHERE d.review_due_at < (snapshot_at AT TIME ZONE 'UTC')::date
    UNION ALL SELECT 'feedback',f.id,NULL::uuid,'Employee feedback',2 FROM app.user_feedback f
      WHERE f.rating=1 AND (f.user_id=caller_user_id OR f.share_with_reviewers)
      AND app.knowledge_run_review_allowed(caller_user_id,caller_role,f.run_id)
    UNION ALL SELECT r.knowledge_result->>'outcome',r.id,NULL::uuid,
      CASE WHEN r.knowledge_result->>'outcome'='conflicting_evidence' THEN 'Conflicting evidence' ELSE 'Insufficient evidence' END,
      CASE WHEN r.knowledge_result->>'outcome'='conflicting_evidence' THEN 1 ELSE 3 END
      FROM app.runs r WHERE r.knowledge_result->>'outcome' IN ('insufficient_evidence','conflicting_evidence')
      AND app.knowledge_run_review_allowed(caller_user_id,caller_role,r.id)
  ), open_items AS MATERIALIZED (
    SELECT c.* FROM candidates c LEFT JOIN app.knowledge_maintenance_reviews m USING(kind,source_id)
    WHERE COALESCE(m.status,'open')='open'
  )
  SELECT jsonb_build_object(
    'generated_at',snapshot_at,'period_start',start_at,'days',p_days,'timezone','UTC',
    'reliability_enabled',COALESCE((SELECT knowledge_reliability_enabled FROM app.company_settings LIMIT 1),false),
    'summary',jsonb_build_object(
      'questions',(SELECT count(*) FROM query_runs),
      'completed',(SELECT count(*) FROM query_runs WHERE status='completed'),
      'failed',(SELECT count(*) FROM query_runs WHERE status='failed'),
      'cancelled',(SELECT count(*) FROM query_runs WHERE status='cancelled'),
      'measured',(SELECT COALESCE(sum(n),0) FROM outcomes),
      'supported',(SELECT COALESCE(sum(n) FILTER(WHERE outcome='supported'),0) FROM outcomes),
      'not_measured',(SELECT count(*) FROM query_runs WHERE status='completed' AND
        COALESCE(knowledge_result->>'outcome','') NOT IN ('supported','partial','insufficient_evidence','conflicting_evidence')),
      'median_response_seconds',(SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM completed_at-created_at))
        FROM query_runs WHERE status='completed' AND completed_at >= created_at AND completed_at <= snapshot_at),
      'latency_samples',(SELECT count(*) FROM query_runs WHERE status='completed' AND completed_at >= created_at AND completed_at <= snapshot_at),
      'cost_usd',(SELECT COALESCE(sum(cost),0)::text FROM daily_cost)),
    'daily',(SELECT jsonb_agg(jsonb_build_object('date',g.day::date,'questions',COALESCE(r.questions,0),'cost_usd',COALESCE(c.cost,0)::text) ORDER BY g.day)
      FROM generate_series(start_at AT TIME ZONE 'UTC',snapshot_at AT TIME ZONE 'UTC',interval '1 day') g(day)
      LEFT JOIN daily_runs r ON r.day=g.day::date LEFT JOIN daily_cost c ON c.day=g.day::date),
    'outcomes',COALESCE((SELECT jsonb_object_agg(outcome,n) FROM outcomes),'{}'::jsonb),
    'authority',COALESCE((SELECT jsonb_object_agg(authority_status,n) FROM
      (SELECT authority_status,count(*) n FROM visible_documents WHERE authority_status IS NOT NULL GROUP BY 1) counts),'{}'::jsonb),
    'authority_unversioned',(SELECT count(*) FROM visible_documents WHERE authority_status IS NULL),
    'attention_counts',COALESCE((SELECT jsonb_object_agg(kind,n) FROM (SELECT kind,count(*) n FROM open_items GROUP BY 1) counts),'{}'::jsonb),
    'attention_items',COALESCE((SELECT jsonb_agg(jsonb_build_object('kind',kind,'source_id',source_id,'document_id',document_id,'title',title) ORDER BY priority,source_id)
      FROM (SELECT * FROM open_items ORDER BY priority,source_id LIMIT 5) top_items),'[]'::jsonb)
  ) INTO result;
  RETURN result;
END; $fn$;
REVOKE ALL ON FUNCTION app.admin_overview(uuid,text,bigint,integer) FROM PUBLIC,anon,authenticated,app_worker;
GRANT EXECUTE ON FUNCTION app.admin_overview(uuid,text,bigint,integer) TO app_api;
COMMENT ON FUNCTION app.admin_overview(uuid,text,bigint,integer) IS
  'Owner/admin anonymous activity and recorded-cost aggregates; only ACL/consent-visible maintenance metadata. No conversation content.';
