-- Keep immutable reservations/allowances separate from observed provider tokens.
CREATE TABLE app.usage_token_measurements (
  usage_id uuid PRIMARY KEY REFERENCES app.llm_usage(id),
  prompt_tokens integer NOT NULL CHECK(prompt_tokens>=0),
  completion_tokens integer NOT NULL CHECK(completion_tokens>=0),
  cached_prompt_tokens integer NOT NULL CHECK(cached_prompt_tokens>=0 AND cached_prompt_tokens<=prompt_tokens),
  cache_write_30m_tokens integer CHECK(cache_write_30m_tokens>=0),
  cache_write_12h_tokens integer CHECK(cache_write_12h_tokens>=0),
  service_tier text CHECK(length(service_tier)<=64),
  CHECK(cached_prompt_tokens+COALESCE(cache_write_30m_tokens,0)+COALESCE(cache_write_12h_tokens,0)<=prompt_tokens)
);
ALTER TABLE app.usage_token_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.usage_token_measurements FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.usage_token_measurements FROM PUBLIC,anon,authenticated,app_api,app_worker;
CREATE TRIGGER usage_token_measurements_immutable BEFORE UPDATE OR DELETE ON app.usage_token_measurements
FOR EACH ROW EXECUTE FUNCTION app.block_llm_usage_mutation();

CREATE FUNCTION app.record_usage_token_measurement(p_user uuid,p_role text,p_authz bigint,
  p_usage uuid,p_input integer,p_output integer,p_cached integer,
  p_write_30m integer DEFAULT NULL,p_write_12h integer DEFAULT NULL,p_tier text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $fn$
BEGIN
  IF NOT app.validate_caller_context(p_user,p_role,p_authz) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected'; END IF;
  IF NOT EXISTS(SELECT 1 FROM app.llm_usage WHERE id=p_usage AND user_id=p_user
    AND NOT timeout_after_send AND prompt_tokens=p_input AND completion_tokens=p_output) THEN
    RAISE EXCEPTION 'query_admission:run_forbidden'; END IF;
  INSERT INTO app.usage_token_measurements VALUES(p_usage,p_input,p_output,p_cached,p_write_30m,p_write_12h,p_tier) ON CONFLICT DO NOTHING;
  IF NOT EXISTS(SELECT 1 FROM app.usage_token_measurements WHERE usage_id=p_usage
    AND prompt_tokens=p_input AND completion_tokens=p_output AND cached_prompt_tokens=p_cached
    AND cache_write_30m_tokens IS NOT DISTINCT FROM p_write_30m
    AND cache_write_12h_tokens IS NOT DISTINCT FROM p_write_12h
    AND service_tier IS NOT DISTINCT FROM p_tier) THEN
    RAISE EXCEPTION 'query_admission:token_measurement_conflict'; END IF;
END; $fn$;
REVOKE ALL ON FUNCTION app.record_usage_token_measurement(uuid,text,bigint,uuid,integer,integer,integer,integer,integer,text) FROM PUBLIC,anon,authenticated,app_worker;
GRANT EXECUTE ON FUNCTION app.record_usage_token_measurement(uuid,text,bigint,uuid,integer,integer,integer,integer,integer,text) TO app_api;

CREATE OR REPLACE FUNCTION app.usage_report_summary(p_start timestamptz,p_end timestamptz,p_user uuid,p_run uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,app AS $fn$
SELECT jsonb_build_object(
 'estimated_cost_usd',CASE WHEN count(c.estimated_usd)>0 OR count(*)=0 THEN COALESCE(sum(c.estimated_usd),0)::text ELSE NULL END,
 'safety_allowance_usd',COALESCE(sum(c.safety_usd),0)::text,
 'unresolved_operations',COALESCE(sum(c.unresolved),0),
 'reconstructed_operations',COALESCE(sum(c.reconstructed),0),
 'estimated_operations',count(c.estimated_usd),
 'budget_accounted_usd',COALESCE(sum(u.cost_usd),0)::text,
 'measured_prompt_tokens',CASE WHEN count(m.usage_id)>0 OR count(*)=0 THEN COALESCE(sum(m.prompt_tokens),0) ELSE NULL END,
 'measured_completion_tokens',CASE WHEN count(m.usage_id)>0 OR count(*)=0 THEN COALESCE(sum(m.completion_tokens),0) ELSE NULL END,
 'unmeasured_operations',count(*)-count(m.usage_id),
 'pricing_basis','Provider token rates where captured; legacy Standard uncached reconstructions. Not a verified provider invoice')
FROM app.llm_usage u CROSS JOIN LATERAL app.classify_usage_cost(u) c
LEFT JOIN app.usage_token_measurements m ON m.usage_id=u.id
WHERE u.recorded_at>=p_start AND u.recorded_at<=p_end
 AND (p_user IS NULL OR u.user_id=p_user) AND (p_run IS NULL OR u.run_id=p_run);
$fn$;

-- Creator-only reporting; authorization is identical to the existing run summary.
CREATE FUNCTION app.run_usage_cost_reporting(p_user uuid,p_role text,p_authz bigint,p_run uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $fn$
BEGIN
  PERFORM app.summarize_run_usage(p_user,p_role,p_authz,p_run);
  RETURN app.usage_report_summary('-infinity','infinity',p_user,p_run);
END; $fn$;
REVOKE ALL ON FUNCTION app.run_usage_cost_reporting(uuid,text,bigint,uuid) FROM PUBLIC,anon,authenticated,app_worker;
GRANT EXECUTE ON FUNCTION app.run_usage_cost_reporting(uuid,text,bigint,uuid) TO app_api;
