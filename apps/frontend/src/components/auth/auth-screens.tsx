/**
 * Auth-direct forms using P08-01 primitives. English chrome. No Stitch frames.
 */

"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { CodeText, UserText } from "../ui/user-text";
import { fetchReady, fetchMeta, acceptInvitation } from "../../lib/api";
import { createBrowserSupabase } from "../../lib/auth/browser";
import {
  CALLBACK_FAILED,
  GOOGLE_OAUTH_BUTTON_LABEL,
  GOOGLE_OAUTH_HELPER,
  MFA_RECOVERY_UNAVAILABLE,
  MFA_REQUIRED_BANNER,
  OWNER_BOOTSTRAP_UNAVAILABLE,
  RESET_EMAIL_SENT,
  SIGN_IN_FAILED,
  SIGN_UP_SUCCESS,
} from "../../lib/auth/copy";
import { GOOGLE_OAUTH_ENABLED, maybeSignInWithGoogle } from "../../lib/auth/google";
import { totpQrImageSrc } from "../../lib/auth/totp-qr";
import { useSession } from "../../lib/auth/session-provider";
import { publicSupabaseConfig } from "../../lib/env";
import { evaluatePaidHandshake, handshakeBelowMinCopy } from "../../lib/handshake";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { publicQueryKeys } from "../../lib/query-keys";
import { ReadinessPanel, SignedOutageCopy } from "../readiness-panel";
import { ReviewedContentFixtures } from "../ui/reviewed-content-fixtures";
import styles from "../developer-app.module.css";

/**
 * Env-missing banner for Auth screens.
 *
 * @returns Banner, or null when public config is present.
 */
export function EnvMissingBanner() {
  if (publicSupabaseConfig() !== null) {
    return null;
  }
  return (
    <StatusBanner kind="error" role="alert">
      Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
    </StatusBanner>
  );
}

/**
 * Handshake-before-spend banner on Auth and console surfaces.
 *
 * @returns Banner when the client is below min or meta is unreachable.
 */
export function HandshakeBanner() {
  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
  });
  const decision = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );
  if (decision.kind === "below_min") {
    return (
      <StatusBanner kind="error" role="alert">
        {handshakeBelowMinCopy()}
      </StatusBanner>
    );
  }
  if (decision.kind === "unreachable") {
    return (
      <StatusBanner kind="warning" role="status">
        Compatibility handshake is unreachable. New paid questions are blocked
        until GET /api/meta succeeds.
      </StatusBanner>
    );
  }
  if (decision.kind === "schema_newer") {
    return (
      <StatusBanner kind="info" role="status">
        API SSE schema is newer than this client catalog. Unknown events are
        ignored.
      </StatusBanner>
    );
  }
  return null;
}

/**
 * Disabled Google OAuth control (GAP-07-04).
 *
 * @returns Disabled button plus helper. Never calls `signInWithOAuth`.
 */
export function GoogleOAuthButton() {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const onClick = useCallback(() => {
    void maybeSignInWithGoogle(GOOGLE_OAUTH_ENABLED, () => {
      if (supabase === null) {
        return Promise.resolve(null);
      }
      return supabase.auth.signInWithOAuth({ provider: "google" });
    });
  }, [supabase]);
  return (
    <div className={styles.panel}>
      <Button type="button" disabled onClick={onClick}>
        {GOOGLE_OAUTH_BUTTON_LABEL}
      </Button>
      <p className={styles.muted}>{GOOGLE_OAUTH_HELPER}</p>
    </div>
  );
}

/**
 * Email/password sign-in. Generic failure only. FastAPI does not throttle this form.
 *
 * @param props - `callbackError` when `/auth/callback` redirected here.
 * @returns Sign-in form.
 */
export function SignInForm({ callbackError = false }: { callbackError?: boolean }) {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const readyQuery = useQuery({
    queryKey: publicQueryKeys.ready,
    queryFn: () => fetchReady(),
    refetchInterval: 5000,
  });

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (supabase === null) {
        setFailed(true);
        return;
      }
      const result = await supabase.auth.signInWithPassword({ email, password });
      if (result.error || !result.data.session?.access_token) {
        setFailed(true);
      }
    },
    [email, password, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>Sign in</h1>
      <p className={styles.muted}>
        Browser-direct Supabase Auth. FastAPI does not rate-limit this form
        (GAP-07-20). Membership still requires an accepted invitation.
      </p>
      <EnvMissingBanner />
      {callbackError ? (
        <StatusBanner kind="error" role="alert">
          {CALLBACK_FAILED}
        </StatusBanner>
      ) : null}
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      <HandshakeBanner />
      <StatusBanner kind="info" role="status">
        {OWNER_BOOTSTRAP_UNAVAILABLE}
      </StatusBanner>
      <ReadinessPanel ready={readyQuery.data} />
      <SignedOutageCopy />
      <ReviewedContentFixtures />
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <Button type="submit" variant="primary">
          Sign in
        </Button>
      </form>
      <GoogleOAuthButton />
      <p className={styles.muted}>
        <Link href="/signup">Sign up</Link>
        {" · "}
        <Link href="/forgot-password">Forgot password</Link>
        {" · "}
        <Link href="/invitations/accept">Accept invitation</Link>
      </p>
    </div>
  );
}

/**
 * Email/password sign-up. Success is not a dashboard.
 *
 * @returns Sign-up form.
 */
export function SignUpForm() {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [failed, setFailed] = useState(false);
  const [success, setSuccess] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (password !== confirm || supabase === null) {
        setFailed(true);
        return;
      }
      const result = await supabase.auth.signUp({ email, password });
      if (result.error) {
        setFailed(true);
        return;
      }
      setSuccess(true);
    },
    [confirm, email, password, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>Sign up</h1>
      <p className={styles.muted}>
        Creates an Auth user. FastAPI membership still needs an invitation.
      </p>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {success ? (
        <StatusBanner kind="success" role="status">
          {SIGN_UP_SUCCESS}
        </StatusBanner>
      ) : null}
      {success ? (
        <p className={styles.muted}>
          Signed up as <UserText value={email} />.
        </p>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <Input
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          required
        />
        <Button type="submit" variant="primary">
          Sign up
        </Button>
      </form>
      <p className={styles.muted}>
        <Link href="/login">Sign in</Link>
        {" · "}
        <Link href="/invitations/accept">Accept invitation</Link>
      </p>
    </div>
  );
}

/**
 * Request a password-reset email. Always shows check-inbox copy after submit.
 *
 * @returns Forgot-password form.
 */
export function ForgotPasswordForm() {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (supabase !== null) {
        const origin = window.location.origin;
        await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${origin}/auth/callback?next=/auth/reset`,
        });
      }
      setSent(true);
    },
    [email, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>Forgot password</h1>
      <EnvMissingBanner />
      {sent ? (
        <StatusBanner kind="info" role="status">
          {RESET_EMAIL_SENT}
        </StatusBanner>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Button type="submit" variant="primary">
          Send reset link
        </Button>
      </form>
      <p className={styles.muted}>
        <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}

/**
 * Set a new password after a recovery callback.
 *
 * @returns Update-password form.
 */
export function ResetPasswordForm() {
  const { supabase } = useSession();
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [updated, setUpdated] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (supabase === null) {
        setFailed(true);
        return;
      }
      const result = await supabase.auth.updateUser({ password });
      if (result.error) {
        setFailed(true);
        return;
      }
      setUpdated(true);
    },
    [password, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>Reset password</h1>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {updated ? (
        <StatusBanner kind="success" role="status">
          Password updated. Continue to the console.
        </StatusBanner>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <Button type="submit" variant="primary">
          Update password
        </Button>
      </form>
      <p className={styles.muted}>
        <Link href="/">Console</Link>
      </p>
    </div>
  );
}

/**
 * TOTP enrollment for aal1 sessions.
 *
 * @returns Enroll form. QR is an img only for data-URL `qr_code`.
 */
export function MfaEnrollForm() {
  const { supabase, signOut } = useSession();
  const [secret, setSecret] = useState<string | null>(null);
  const [qrSrc, setQrSrc] = useState<string | null>(null);
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [failed, setFailed] = useState(false);
  const [verified, setVerified] = useState(false);

  const startEnroll = useCallback(async () => {
    setFailed(false);
    if (supabase === null) {
      setFailed(true);
      return;
    }
    const enrolled = await supabase.auth.mfa.enroll({ factorType: "totp" });
    if (enrolled.error || enrolled.data.type !== "totp") {
      setFailed(true);
      return;
    }
    setFactorId(enrolled.data.id);
    setSecret(enrolled.data.totp.secret);
    setQrSrc(totpQrImageSrc(enrolled.data.totp.qr_code));
  }, [supabase]);

  const verify = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (supabase === null || factorId === null) {
        setFailed(true);
        return;
      }
      const challenge = await supabase.auth.mfa.challenge({ factorId });
      if (challenge.error) {
        setFailed(true);
        return;
      }
      const verifiedResult = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challenge.data.id,
        code,
      });
      if (verifiedResult.error) {
        setFailed(true);
        return;
      }
      setVerified(true);
    },
    [code, factorId, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>Enroll MFA</h1>
      <StatusBanner kind="error" role="alert">
        {MFA_REQUIRED_BANNER}
      </StatusBanner>
      <StatusBanner kind="warning" role="status">
        {MFA_RECOVERY_UNAVAILABLE}
      </StatusBanner>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {verified ? (
        <StatusBanner kind="success" role="status">
          TOTP verified. The session should now be aal2.
        </StatusBanner>
      ) : null}
      <div className={styles.row}>
        <Button type="button" variant="primary" onClick={() => void startEnroll()}>
          Start TOTP enrollment
        </Button>
        <Button type="button" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
      {qrSrc ? (
        // enroll totp.qr_code was already a data URL. Never inject raw SVG HTML.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={qrSrc} alt="TOTP QR code" width={160} height={160} />
      ) : null}
      {secret ? (
        <p className={styles.muted}>
          Authenticator secret: <CodeText value={secret} />
        </p>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void verify(event)}>
        <Input
          label="Authenticator code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          required
        />
        <Button type="submit" variant="primary">
          Verify TOTP
        </Button>
      </form>
      <p className={styles.muted}>
        <Link href="/mfa/challenge">Challenge an existing factor</Link>
        {" · "}
        <Link href="/unavailable/GAP-07-07">Unavailable GAP-07-07</Link>
      </p>
    </div>
  );
}

/**
 * TOTP challenge for verified factors at aal1.
 *
 * @returns Challenge form. No fake success without Auth verify.
 */
export function MfaChallengeForm() {
  const { supabase, signOut } = useSession();
  const [code, setCode] = useState("");
  const [failed, setFailed] = useState(false);
  const [verified, setVerified] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (supabase === null) {
        setFailed(true);
        return;
      }
      const factors = await supabase.auth.mfa.listFactors();
      const totp = factors.data?.totp[0];
      if (factors.error || totp === undefined) {
        setFailed(true);
        return;
      }
      const challenge = await supabase.auth.mfa.challenge({ factorId: totp.id });
      if (challenge.error) {
        setFailed(true);
        return;
      }
      const verifiedResult = await supabase.auth.mfa.verify({
        factorId: totp.id,
        challengeId: challenge.data.id,
        code,
      });
      if (verifiedResult.error) {
        setFailed(true);
        return;
      }
      setVerified(true);
    },
    [code, supabase],
  );

  return (
    <div className={styles.shell}>
      <h1>MFA challenge</h1>
      <StatusBanner kind="error" role="alert">
        {MFA_REQUIRED_BANNER}
      </StatusBanner>
      <StatusBanner kind="warning" role="status">
        {MFA_RECOVERY_UNAVAILABLE}
      </StatusBanner>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {verified ? (
        <StatusBanner kind="success" role="status">
          TOTP verified. The session should now be aal2.
        </StatusBanner>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Authenticator code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          required
        />
        <div className={styles.row}>
          <Button type="submit" variant="primary">
            Verify TOTP
          </Button>
          <Button type="button" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </form>
      <p className={styles.muted}>
        <Link href="/mfa/enroll">Enroll TOTP</Link>
        {" · "}
        <Link href="/unavailable/GAP-07-07">Unavailable GAP-07-07</Link>
      </p>
    </div>
  );
}

/**
 * Authenticated invitation accept. Posts `{ token }` only.
 *
 * @returns Accept form.
 */
export function InvitationAcceptForm() {
  const { accessToken, email, supabase } = useSession();
  const [token, setToken] = useState("");
  const [invitationId, setInvitationId] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(null);
      if (accessToken === null) {
        setFailed("Sign in before accepting an invitation.");
        return;
      }
      try {
        const accepted = await acceptInvitation({ accessToken }, token);
        setInvitationId(accepted.invitation_id);
      } catch (error) {
        setFailed(
          error instanceof Error
            ? mutationFailureBanner(error)
            : mutationFailureBanner(new Error("invitation_rejected")),
        );
      }
    },
    [accessToken, token],
  );

  return (
    <div className={styles.shell}>
      <h1>Accept invitation</h1>
      <p className={styles.muted}>
        Email comes from the signed-in JWT, not this form. Team create/offboard
        is a later packet.
      </p>
      <StatusBanner kind="info" role="status">
        {OWNER_BOOTSTRAP_UNAVAILABLE}
      </StatusBanner>
      <EnvMissingBanner />
      {accessToken === null ? (
        <StatusBanner kind="warning" role="status">
          Sign in, then paste the invitation token.
        </StatusBanner>
      ) : (
        <p className={styles.muted}>
          Signed in as <UserText value={email ?? ""} />.
        </p>
      )}
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {failed}
        </StatusBanner>
      ) : null}
      {invitationId ? (
        <StatusBanner kind="success" role="status">
          Invitation accepted: <CodeText value={invitationId} />
        </StatusBanner>
      ) : null}
      <form className={styles.panel} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Invitation token"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          minLength={8}
          required
        />
        <Button type="submit" variant="primary" disabled={accessToken === null}>
          Accept invitation
        </Button>
      </form>
      <p className={styles.muted}>
        <Link href="/login">Sign in</Link>
        {" · "}
        <Link href="/unavailable/GAP-07-08">Unavailable GAP-07-08</Link>
      </p>
      {supabase === null ? <EnvMissingBanner /> : null}
    </div>
  );
}

const KNOWN_GAPS = {
  "GAP-07-07": MFA_RECOVERY_UNAVAILABLE,
  "GAP-07-08": OWNER_BOOTSTRAP_UNAVAILABLE,
} as const;

export type KnownUnavailableGap = keyof typeof KNOWN_GAPS;

/**
 * Honest Unavailable surface. No mocked HTTP, no recovery-code inputs.
 *
 * @param props - Gap id from the route.
 * @returns Gap copy only.
 */
export function UnavailableGap({ gap }: { gap: string }) {
  const copy =
    gap in KNOWN_GAPS
      ? KNOWN_GAPS[gap as KnownUnavailableGap]
      : "This surface is unavailable. No mocked API is provided.";
  return (
    <div className={styles.shell}>
      <h1>Unavailable</h1>
      <StatusBanner kind="warning" role="status">
        {copy}
      </StatusBanner>
      <p className={styles.muted}>
        Gap id: <CodeText value={gap} />
      </p>
      <p className={styles.muted}>
        <Link href="/login">Sign in</Link>
        {" · "}
        <Link href="/invitations/accept">Accept invitation</Link>
      </p>
    </div>
  );
}
