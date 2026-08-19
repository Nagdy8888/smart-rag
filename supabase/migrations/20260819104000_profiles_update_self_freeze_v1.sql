-- PRD-L-012: Self-update must freeze upload_enabled, mfa_enrolled, and
-- disabled_at in addition to role.

DROP POLICY IF EXISTS profiles_update_self_non_role ON app.profiles;

CREATE POLICY profiles_update_self_non_role
  ON app.profiles
  FOR UPDATE
  TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (
    user_id = auth.uid()
    AND role = (
      SELECT p.role
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
    )
    AND upload_enabled = (
      SELECT p.upload_enabled
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
    )
    AND mfa_enrolled = (
      SELECT p.mfa_enrolled
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
    )
    AND disabled_at IS NOT DISTINCT FROM (
      SELECT p.disabled_at
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
    )
  );
