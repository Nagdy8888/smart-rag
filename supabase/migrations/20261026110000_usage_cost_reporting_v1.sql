-- Reporting corrections never update ledger charges or reservation accounting.
CREATE TABLE app.usage_cost_basis (
  usage_id uuid PRIMARY KEY REFERENCES app.llm_usage(id),
  basis text NOT NULL CHECK (basis IN ('supplied_cost_estimate','standard_token_estimate','safety_allowance')),
  estimated_cost_usd numeric(18,8) CHECK (estimated_cost_usd >= 0),
  pricing_version text NOT NULL DEFAULT 'standard-2026-10-26-uncached',
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((basis='safety_allowance') = (estimated_cost_usd IS NULL))
);
ALTER TABLE app.usage_cost_basis ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.usage_cost_basis FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.usage_cost_basis FROM PUBLIC,anon,authenticated,app_api,app_worker;
CREATE TRIGGER usage_cost_basis_immutable BEFORE UPDATE OR DELETE ON app.usage_cost_basis
FOR EACH ROW EXECUTE FUNCTION app.block_llm_usage_mutation();

CREATE FUNCTION app.record_usage_cost_basis(p_user uuid,p_role text,p_authz bigint,
  p_usage_id uuid,p_basis text,p_estimate numeric) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $fn$
BEGIN
  IF NOT app.validate_caller_context(p_user,p_role,p_authz) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected'; END IF;
  IF NOT EXISTS(SELECT 1 FROM app.llm_usage WHERE id=p_usage_id AND user_id=p_user) THEN
    RAISE EXCEPTION 'query_admission:run_forbidden'; END IF;
  INSERT INTO app.usage_cost_basis(usage_id,basis,estimated_cost_usd,pricing_version)
  VALUES(p_usage_id,p_basis,p_estimate,CASE p_basis WHEN 'supplied_cost_estimate' THEN 'supplied-cost-estimate' WHEN 'safety_allowance' THEN 'unresolved' ELSE 'standard-2026-10-26-uncached' END) ON CONFLICT DO NOTHING;
  IF NOT EXISTS(SELECT 1 FROM app.usage_cost_basis WHERE usage_id=p_usage_id
    AND basis=p_basis AND estimated_cost_usd IS NOT DISTINCT FROM p_estimate) THEN
    RAISE EXCEPTION 'query_admission:cost_basis_conflict'; END IF;
END; $fn$;
REVOKE ALL ON FUNCTION app.record_usage_cost_basis(uuid,text,bigint,uuid,text,numeric) FROM PUBLIC,anon,authenticated,app_worker;
GRANT EXECUTE ON FUNCTION app.record_usage_cost_basis(uuid,text,bigint,uuid,text,numeric) TO app_api;

CREATE FUNCTION app.standard_token_cost_20261026(p_model text,p_kind text,p_input integer,p_output integer)
RETURNS numeric LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $fn$
SELECT CASE WHEN p_input<0 OR p_output<0 THEN NULL
  WHEN p_kind='embedding' AND p_model='text-embedding-3-large' THEN round(p_input*0.13/1000000,8)
  WHEN p_kind='embedding' THEN NULL
  WHEN p_model='gpt-6-luna' THEN round((p_input*0.10*CASE WHEN p_input>272000 THEN 2 ELSE 1 END
    +p_output*0.50*CASE WHEN p_input>272000 THEN 1.5 ELSE 1 END)/1000000,8)
  WHEN p_model IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18') THEN round((p_input*0.15+p_output*0.60)/1000000,8)
  WHEN p_model IN ('gpt-4.1-mini','gpt-4.1-mini-2025-04-14') THEN round((p_input*0.40+p_output*1.60)/1000000,8)
  WHEN p_model='gpt-5.4-mini' THEN round((p_input*0.75+p_output*4.50)/1000000,8)
  ELSE NULL END;
$fn$;
REVOKE ALL ON FUNCTION app.standard_token_cost_20261026(text,text,integer,integer) FROM PUBLIC,anon,authenticated,app_api,app_worker;

CREATE FUNCTION app.classify_usage_cost(u app.llm_usage)
RETURNS TABLE(estimated_usd numeric,safety_usd numeric,unresolved integer,reconstructed integer)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,app AS $fn$
WITH basis AS (SELECT b.basis,b.estimated_cost_usd FROM app.usage_cost_basis b WHERE b.usage_id=u.id),
classification AS (
 SELECT CASE
   WHEN u.timeout_after_send THEN NULL
   WHEN EXISTS(SELECT 1 FROM basis) THEN (SELECT estimated_cost_usd FROM basis)
   -- Legacy cap-shaped token counters may be synthetic. Never price these as measured usage.
   WHEN u.prompt_tokens = CASE u.usage_kind WHEN 'profile' THEN 4000 WHEN 'rewrite' THEN 4000 WHEN 'rerank' THEN 12000 WHEN 'verifier' THEN 4000 WHEN 'answer' THEN 8000 WHEN 'summary' THEN 6000 ELSE 8000 END THEN NULL
   WHEN u.usage_kind<>'embedding' AND u.completion_tokens = CASE u.usage_kind WHEN 'profile' THEN 1500 WHEN 'rewrite' THEN 1500 WHEN 'rerank' THEN 2000 WHEN 'verifier' THEN 1000 WHEN 'answer' THEN 2000 WHEN 'summary' THEN 1500 ELSE 2000 END THEN NULL
   WHEN u.prompt_tokens=0 AND u.completion_tokens=0 AND u.cost_usd>0 THEN NULL
   ELSE app.standard_token_cost_20261026(u.model_id,u.usage_kind,u.prompt_tokens,u.completion_tokens)
 END estimated
)
SELECT estimated,CASE WHEN estimated IS NULL THEN u.cost_usd ELSE 0 END,
 CASE WHEN estimated IS NULL THEN 1 ELSE 0 END,
 CASE WHEN estimated IS NOT NULL AND NOT EXISTS(SELECT 1 FROM basis) THEN 1 ELSE 0 END
FROM classification;
$fn$;
REVOKE ALL ON FUNCTION app.classify_usage_cost(app.llm_usage) FROM PUBLIC,anon,authenticated,app_api,app_worker;

CREATE FUNCTION app.usage_report_summary(p_start timestamptz,p_end timestamptz,p_user uuid,p_run uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,app AS $fn$
SELECT jsonb_build_object(
 'estimated_cost_usd',CASE WHEN count(c.estimated_usd)>0 OR count(*)=0 THEN COALESCE(sum(c.estimated_usd),0)::text ELSE NULL END,
 'safety_allowance_usd',COALESCE(sum(c.safety_usd),0)::text,
 'unresolved_operations',COALESCE(sum(c.unresolved),0),
 'reconstructed_operations',COALESCE(sum(c.reconstructed),0),
 'estimated_operations',count(c.estimated_usd),
 'budget_accounted_usd',COALESCE(sum(u.cost_usd),0)::text,
 'pricing_basis','Standard uncached text-token estimates; historical reconstructions are not verified invoices')
FROM app.llm_usage u CROSS JOIN LATERAL app.classify_usage_cost(u) c
WHERE u.recorded_at>=p_start AND u.recorded_at<=p_end
 AND (p_user IS NULL OR u.user_id=p_user) AND (p_run IS NULL OR u.run_id=p_run);
$fn$;
REVOKE ALL ON FUNCTION app.usage_report_summary(timestamptz,timestamptz,uuid,uuid) FROM PUBLIC,anon,authenticated,app_api,app_worker;

CREATE FUNCTION app.summarize_usage_cost_reporting(p_user uuid,p_role text,p_authz bigint,p_company boolean)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $fn$
BEGIN
 IF NOT app.validate_caller_context(p_user,p_role,p_authz) THEN RAISE EXCEPTION 'usage:authorization_rejected'; END IF;
 IF p_company AND p_role NOT IN ('owner','admin') THEN RAISE EXCEPTION 'usage:forbidden'; END IF;
 RETURN app.usage_report_summary('-infinity','infinity',CASE WHEN p_company THEN NULL ELSE p_user END,NULL);
END; $fn$;
REVOKE ALL ON FUNCTION app.summarize_usage_cost_reporting(uuid,text,bigint,boolean) FROM PUBLIC,anon,authenticated,app_worker;
GRANT EXECUTE ON FUNCTION app.summarize_usage_cost_reporting(uuid,text,bigint,boolean) TO app_api;

-- Anonymous company aggregates; document and maintenance details retain ACL/consent.
CREATE OR REPLACE FUNCTION app.admin_overview(caller_user_id uuid, caller_role text,
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
    SELECT (u.recorded_at AT TIME ZONE 'UTC')::date AS day,sum(u.cost_usd) AS cost,
      CASE WHEN count(c.estimated_usd)>0 THEN sum(c.estimated_usd)::text ELSE NULL END AS estimated,
      sum(c.safety_usd)::text AS safety,sum(c.unresolved) AS unresolved,
      sum(c.reconstructed) AS reconstructed,count(c.estimated_usd) AS estimated_operations
    FROM app.llm_usage u CROSS JOIN LATERAL app.classify_usage_cost(u) c
    WHERE u.recorded_at >= start_at AND u.recorded_at <= snapshot_at GROUP BY 1
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
      'cost_usd',(SELECT COALESCE(sum(cost),0)::text FROM daily_cost),
      'cost_reporting',app.usage_report_summary(start_at,snapshot_at,NULL,NULL)),
    'daily',(SELECT jsonb_agg(jsonb_build_object('date',g.day::date,'questions',COALESCE(r.questions,0),'cost_usd',COALESCE(c.cost,0)::text,
      'cost_reporting',jsonb_build_object('estimated_cost_usd',CASE WHEN c.day IS NULL THEN '0' ELSE c.estimated END,
        'safety_allowance_usd',COALESCE(c.safety,'0'),'unresolved_operations',COALESCE(c.unresolved,0),
        'reconstructed_operations',COALESCE(c.reconstructed,0),'estimated_operations',COALESCE(c.estimated_operations,0),
        'budget_accounted_usd',COALESCE(c.cost,0)::text,'pricing_basis','Standard uncached text-token estimates; historical reconstructions are not verified invoices')) ORDER BY g.day)
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
