-- Unknown-only checkpoint buckets remain gaps rather than zero-dollar claims.
CREATE OR REPLACE FUNCTION app.admin_overview(caller_user_id uuid,caller_role text,
 caller_authorization_version bigint,p_days integer DEFAULT 30)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app
SET statement_timeout='10s' AS $fn$
DECLARE payload jsonb; history jsonb; bucket jsonb; daily jsonb := '[]'; ledger numeric; extra numeric;
BEGIN
 payload := app.admin_overview_ledger_v1(caller_user_id,caller_role,caller_authorization_version,p_days);
 history := app.checkpoint_usage_summary((payload->>'period_start')::timestamptz,(payload->>'generated_at')::timestamptz,NULL);
 ledger := (payload#>>'{summary,cost_reporting,estimated_cost_usd}')::numeric;
 extra := (history->>'additional_estimated_cost_usd')::numeric;
 IF ledger=0 AND extra IS NULL AND (history->>'runs')::bigint>(history->>'overlapping_ledger_runs')::bigint THEN
   IF COALESCE((payload#>>'{summary,cost_reporting,estimated_operations}')::bigint,0)=0 THEN ledger:=NULL; END IF;
 END IF;
 payload := jsonb_set(payload,'{summary,display_cost_usd}',COALESCE(to_jsonb(CASE WHEN ledger IS NULL AND extra IS NULL THEN NULL ELSE COALESCE(ledger,0)+COALESCE(extra,0) END::text),'null'::jsonb),true);
 payload := jsonb_set(payload,'{summary,checkpoint_usage}',history,true);
 FOR bucket IN SELECT value FROM jsonb_array_elements(payload->'daily') LOOP
   history := app.checkpoint_usage_summary((bucket->>'date')::date::timestamp AT TIME ZONE 'UTC',
     LEAST(((bucket->>'date')::date+1)::timestamp AT TIME ZONE 'UTC',(payload->>'generated_at')::timestamptz),NULL);
   ledger := (bucket#>>'{cost_reporting,estimated_cost_usd}')::numeric;
   extra := (history->>'additional_estimated_cost_usd')::numeric;
 IF ledger=0 AND extra IS NULL AND (history->>'runs')::bigint>(history->>'overlapping_ledger_runs')::bigint THEN
   IF COALESCE((bucket#>>'{cost_reporting,estimated_operations}')::bigint,0)=0 THEN ledger:=NULL; END IF;
 END IF;
   bucket := jsonb_set(bucket,'{display_cost_usd}',COALESCE(to_jsonb(CASE WHEN ledger IS NULL AND extra IS NULL THEN NULL ELSE COALESCE(ledger,0)+COALESCE(extra,0) END::text),'null'::jsonb),true);
   daily := daily || jsonb_build_array(bucket);
 END LOOP;
 RETURN jsonb_set(payload,'{daily}',daily);
END; $fn$;
REVOKE ALL ON FUNCTION app.admin_overview(uuid,text,bigint,integer) FROM PUBLIC,anon,authenticated,app_worker,app_checkpointer;
GRANT EXECUTE ON FUNCTION app.admin_overview(uuid,text,bigint,integer) TO app_api;
