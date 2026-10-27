-- Operator-populated, content-free projections; original checkpoints and ledger stay intact.
CREATE TABLE app.checkpoint_usage_runs (
  run_id uuid PRIMARY KEY,
  source_user_id uuid NOT NULL,
  checkpoint_id text NOT NULL CHECK(length(checkpoint_id) BETWEEN 1 AND 100),
  recorded_at timestamptz NOT NULL,
  prompt_tokens bigint NOT NULL CHECK(prompt_tokens>=0),
  completion_tokens bigint NOT NULL CHECK(completion_tokens>=0),
  stored_cost_usd numeric(18,8) CHECK(stored_cost_usd>=0),
  estimated_cost_usd numeric(18,8) CHECK(estimated_cost_usd>=0),
  cost_state text NOT NULL CHECK(cost_state IN ('recorded_estimate','unrecorded','allowance_possible')),
  CHECK((cost_state='recorded_estimate')=(estimated_cost_usd IS NOT NULL))
);
CREATE INDEX checkpoint_usage_runs_recorded_idx ON app.checkpoint_usage_runs(recorded_at);
CREATE INDEX checkpoint_usage_runs_user_idx ON app.checkpoint_usage_runs(source_user_id);
ALTER TABLE app.checkpoint_usage_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.checkpoint_usage_runs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.checkpoint_usage_runs FROM PUBLIC,anon,authenticated,app_api,app_worker,app_checkpointer;

CREATE FUNCTION app.checkpoint_usage_summary(p_start timestamptz,p_end timestamptz,p_user uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,app AS $fn$
WITH scoped AS (
 SELECT h.*,
 EXISTS(SELECT 1 FROM app.llm_usage u WHERE u.run_id=h.run_id) AS in_ledger,
 EXISTS(SELECT 1 FROM app.llm_usage u JOIN app.usage_token_measurements m ON m.usage_id=u.id WHERE u.run_id=h.run_id) AS has_measurement
 FROM app.checkpoint_usage_runs h WHERE recorded_at>=p_start AND recorded_at<p_end
 AND (p_user IS NULL OR source_user_id=p_user)
)
SELECT jsonb_build_object(
 'runs',count(*),'prompt_tokens',COALESCE(sum(prompt_tokens),0),
 'completion_tokens',COALESCE(sum(completion_tokens),0),
 'estimated_cost_usd',CASE WHEN count(estimated_cost_usd)>0 OR count(*)=0 THEN COALESCE(sum(estimated_cost_usd),0)::text ELSE NULL END,
 'unpriced_runs',count(*) FILTER(WHERE estimated_cost_usd IS NULL),
 'overlapping_ledger_runs',count(*) FILTER(WHERE in_ledger),
 'additional_prompt_tokens',COALESCE(sum(prompt_tokens) FILTER(WHERE NOT has_measurement),0),
 'additional_completion_tokens',COALESCE(sum(completion_tokens) FILTER(WHERE NOT has_measurement),0),
 'additional_estimated_cost_usd',(sum(estimated_cost_usd) FILTER(WHERE NOT in_ledger))::text,
 'first_recorded_at',min(recorded_at),'last_recorded_at',max(recorded_at)) FROM scoped;
$fn$;
REVOKE ALL ON FUNCTION app.checkpoint_usage_summary(timestamptz,timestamptz,uuid) FROM PUBLIC,anon,authenticated,app_api,app_worker,app_checkpointer;

CREATE FUNCTION app.summarize_checkpoint_usage(p_user uuid,p_role text,p_authz bigint,p_company boolean)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $fn$
BEGIN
 IF NOT app.validate_caller_context(p_user,p_role,p_authz) THEN RAISE EXCEPTION 'usage:authorization_rejected'; END IF;
 IF p_company IS NULL OR (p_company AND p_role NOT IN ('owner','admin')) THEN RAISE EXCEPTION 'usage:forbidden'; END IF;
 RETURN app.checkpoint_usage_summary('-infinity','infinity',CASE WHEN p_company THEN NULL ELSE p_user END);
END; $fn$;
REVOKE ALL ON FUNCTION app.summarize_checkpoint_usage(uuid,text,bigint,boolean) FROM PUBLIC,anon,authenticated,app_worker,app_checkpointer;
GRANT EXECUTE ON FUNCTION app.summarize_checkpoint_usage(uuid,text,bigint,boolean) TO app_api;

-- Extend the established authorized overview without rewriting its ACL/consent rules.
ALTER FUNCTION app.admin_overview(uuid,text,bigint,integer) RENAME TO admin_overview_ledger_v1;
REVOKE ALL ON FUNCTION app.admin_overview_ledger_v1(uuid,text,bigint,integer) FROM app_api;
CREATE FUNCTION app.admin_overview(caller_user_id uuid,caller_role text,
 caller_authorization_version bigint,p_days integer DEFAULT 30)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app
SET statement_timeout='10s' AS $fn$
DECLARE payload jsonb; history jsonb; bucket jsonb; daily jsonb := '[]'; ledger numeric; extra numeric;
BEGIN
 payload := app.admin_overview_ledger_v1(caller_user_id,caller_role,caller_authorization_version,p_days);
 history := app.checkpoint_usage_summary((payload->>'period_start')::timestamptz,(payload->>'generated_at')::timestamptz,NULL);
 ledger := (payload#>>'{summary,cost_reporting,estimated_cost_usd}')::numeric;
 extra := (history->>'additional_estimated_cost_usd')::numeric;
 payload := jsonb_set(payload,'{summary,display_cost_usd}',COALESCE(to_jsonb(CASE WHEN ledger IS NULL AND extra IS NULL THEN NULL ELSE COALESCE(ledger,0)+COALESCE(extra,0) END::text),'null'::jsonb),true);
 payload := jsonb_set(payload,'{summary,checkpoint_usage}',history,true);
 FOR bucket IN SELECT value FROM jsonb_array_elements(payload->'daily') LOOP
   history := app.checkpoint_usage_summary((bucket->>'date')::date::timestamp AT TIME ZONE 'UTC',
     LEAST(((bucket->>'date')::date+1)::timestamp AT TIME ZONE 'UTC',(payload->>'generated_at')::timestamptz),NULL);
   ledger := (bucket#>>'{cost_reporting,estimated_cost_usd}')::numeric;
   extra := (history->>'additional_estimated_cost_usd')::numeric;
   bucket := jsonb_set(bucket,'{display_cost_usd}',COALESCE(to_jsonb(CASE WHEN ledger IS NULL AND extra IS NULL THEN NULL ELSE COALESCE(ledger,0)+COALESCE(extra,0) END::text),'null'::jsonb),true);
   daily := daily || jsonb_build_array(bucket);
 END LOOP;
 RETURN jsonb_set(payload,'{daily}',daily);
END; $fn$;
REVOKE ALL ON FUNCTION app.admin_overview(uuid,text,bigint,integer) FROM PUBLIC,anon,authenticated,app_worker,app_checkpointer;
GRANT EXECUTE ON FUNCTION app.admin_overview(uuid,text,bigint,integer) TO app_api;
