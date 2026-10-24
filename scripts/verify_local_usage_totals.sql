-- Read-only regression check for a populated local development database.
-- Requires an active admin, member, and an admin-owned conversation/run.
-- Run with psql -v ON_ERROR_STOP=1 -f scripts/verify_local_usage_totals.sql.
BEGIN;
DO $test$
DECLARE
  admin_id uuid;
  member_id uuid;
  av bigint;
  actual record;
  expected record;
  owned_run uuid;
BEGIN
  SELECT user_id INTO STRICT admin_id FROM app.profiles WHERE role = 'admin' AND disabled_at IS NULL LIMIT 1;
  SELECT user_id INTO STRICT member_id FROM app.profiles WHERE role = 'member' AND disabled_at IS NULL LIMIT 1;
  SELECT authorization_version INTO STRICT av FROM app.company_settings LIMIT 1;
  SELECT * INTO actual FROM app.summarize_company_usage(admin_id, 'admin', av);
  SELECT COALESCE(sum(cost_usd),0) AS cost_usd, COALESCE(sum(prompt_tokens),0) AS prompt_tokens, COALESCE(sum(completion_tokens),0) AS completion_tokens, count(*) AS usage_rows INTO expected FROM app.llm_usage;
  ASSERT actual = expected, 'company ledger mismatch';
  SELECT * INTO actual FROM app.summarize_caller_usage(admin_id, 'admin', av);
  SELECT COALESCE(sum(cost_usd),0) AS cost_usd, COALESCE(sum(prompt_tokens),0) AS prompt_tokens, COALESCE(sum(completion_tokens),0) AS completion_tokens, count(*) AS usage_rows INTO expected FROM app.llm_usage WHERE user_id = admin_id;
  ASSERT actual = expected, 'caller ledger mismatch';
  SELECT r.id INTO owned_run FROM app.runs r JOIN app.conversations c ON c.id=r.conversation_id WHERE r.creator_user_id=admin_id AND c.deleted_at IS NULL LIMIT 1;
  ASSERT owned_run IS NOT NULL, 'missing owned run fixture';
  SELECT * INTO actual FROM app.summarize_run_usage(admin_id, 'admin', av, owned_run);
  SELECT COALESCE(sum(cost_usd),0) AS cost_usd, COALESCE(sum(prompt_tokens),0) AS prompt_tokens, COALESCE(sum(completion_tokens),0) AS completion_tokens, count(*) AS usage_rows INTO expected FROM app.llm_usage WHERE run_id=owned_run;
  ASSERT actual = expected, 'run ledger mismatch';
  BEGIN
    PERFORM * FROM app.summarize_company_usage(member_id, 'member', av);
    RAISE EXCEPTION 'member unexpectedly allowed';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'usage:forbidden' THEN RAISE; END IF;
  END;
  BEGIN
    PERFORM * FROM app.summarize_caller_usage(admin_id, 'admin', av + 1);
    RAISE EXCEPTION 'stale version unexpectedly allowed';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'usage:authorization_rejected' THEN RAISE; END IF;
  END;
  ASSERT NOT has_function_privilege('authenticated', 'app.summarize_company_usage(uuid,text,bigint)', 'execute');
  ASSERT has_function_privilege('app_api', 'app.summarize_company_usage(uuid,text,bigint)', 'execute');
  RAISE NOTICE 'PASS: caller/company/run totals match ledger; member and stale version denied; execute privileges preserved';
END;
$test$;
ROLLBACK;
