-- Give composite company answers time for the post-verify rewrite.
-- Answer, verifier, and organize each need a provider call. The previous
-- 50 second envelope was spent before organize started, so the verified
-- text was kept unchanged.

CREATE OR REPLACE FUNCTION app.query_route_envelope(p_route_family text)
RETURNS TABLE (
  deadline_seconds integer,
  recursion_limit integer,
  correction_ceiling integer,
  subquestion_ceiling integer,
  model_call_ceiling integer,
  tool_ceiling integer,
  discovery_ceiling integer,
  manifest_ceiling integer,
  side_effect_ceiling integer,
  envelope_usd numeric,
  envelope_prompt_tokens integer,
  envelope_completion_tokens integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  CASE p_route_family
    WHEN 'hybrid' THEN
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    WHEN 'combined' THEN
      deadline_seconds := 45;
      model_call_ceiling := 8;
      tool_ceiling := 4;
      envelope_usd := 3.20;
      envelope_prompt_tokens := 64000;
      envelope_completion_tokens := 16000;
    WHEN 'structured_table' THEN
      deadline_seconds := 30;
      model_call_ceiling := 6;
      tool_ceiling := 4;
      envelope_usd := 2.40;
      envelope_prompt_tokens := 48000;
      envelope_completion_tokens := 12000;
    WHEN 'composite' THEN
      deadline_seconds := 75;
      model_call_ceiling := 9;
      tool_ceiling := 5;
      envelope_usd := 3.60;
      envelope_prompt_tokens := 72000;
      envelope_completion_tokens := 18000;
    WHEN 'graph_inspection' THEN
      deadline_seconds := 10;
      model_call_ceiling := 3;
      tool_ceiling := 4;
      envelope_usd := 0.75;
      envelope_prompt_tokens := 12000;
      envelope_completion_tokens := 4500;
    WHEN 'no_retrieval' THEN
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    WHEN 'scoped_refusal' THEN
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    WHEN 'web_research' THEN
      deadline_seconds := 50;
      model_call_ceiling := 5;
      tool_ceiling := 5;
      envelope_usd := 2.00;
      envelope_prompt_tokens := 40000;
      envelope_completion_tokens := 10000;
    ELSE
      RAISE EXCEPTION 'query_admission:unknown_route_family';
  END CASE;

  recursion_limit := 24;
  IF p_route_family = 'web_research' THEN
    correction_ceiling := 0;
  ELSE
    correction_ceiling := 1;
  END IF;
  subquestion_ceiling := 3;
  discovery_ceiling := 1;
  manifest_ceiling := 3;
  side_effect_ceiling := 1;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.query_route_envelope(text) IS
  'Server-owned Phase 6 route envelopes. Composite is 75s so the verified-answer rewrite can run after answer and verifier.';
