// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { XSS_FILENAME } from "../../lib/hostile-text-fixtures";
import {
  CALLBACK_FAILED,
  OWNER_BOOTSTRAP_UNAVAILABLE,
  RESET_EMAIL_SENT,
  SIGN_IN_FAILED,
} from "../../lib/auth/copy";
import { handshakeBelowMinCopy } from "../../lib/handshake";
import { SessionProvider } from "../../lib/auth/session-provider";
import {
  EnvMissingBanner,
  ForgotPasswordForm,
  HandshakeBanner,
  InvitationAcceptForm,
  ResetPasswordForm,
  SignInForm,
  SignUpForm,
} from "./auth-screens";

afterEach(() => {
  cleanup();
});

const signInWithPassword = vi.fn();
const signInWithOAuth = vi.fn();
const signUp = vi.fn();
const resetPasswordForEmail = vi.fn();
const updateUser = vi.fn();
const getSession = vi.fn(
  async (): Promise<{
    data: { session: { access_token: string; user: { email: string } } | null };
  }> => ({ data: { session: null } }),
);
const onAuthStateChange = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));
const fetchMeta = vi.fn();
const acceptInvitation = vi.fn();
const { envState } = vi.hoisted(() => ({
  envState: { present: true },
}));

vi.mock("../../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      signInWithPassword,
      signInWithOAuth,
      signUp,
      resetPasswordForEmail,
      updateUser,
      getSession,
      onAuthStateChange,
      signOut: vi.fn(),
    },
  }),
}));

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push: vi.fn() }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () =>
    envState.present
      ? {
          url: "http://127.0.0.1:54321",
          anonKey: "anon",
        }
      : null,
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchMeta: (...args: unknown[]) => fetchMeta(...args),
    fetchReady: vi.fn(async () => null),
    acceptInvitation: (...args: unknown[]) => acceptInvitation(...args),
  };
});

beforeEach(() => {
  envState.present = true;
  fetchMeta.mockResolvedValue({
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  });
  acceptInvitation.mockReset();
  resetPasswordForEmail.mockReset();
  updateUser.mockReset();
  getSession.mockResolvedValue({ data: { session: null } });
});

/**
 * Wrap Auth screens with Query and session providers.
 *
 * @param ui - Screen under test.
 * @returns Render result.
 */
function renderAuth(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

describe("SignInForm", () => {
  it("shows a generic Sign in failed banner without provider traces", async () => {
    signInWithPassword.mockResolvedValueOnce({
      error: { message: "AuthApiError: Invalid login credentials from GoTrue" },
      data: { session: null },
    });
    const user = userEvent.setup();
    renderAuth(<SignInForm />);
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(SIGN_IN_FAILED);
    expect(
      screen.queryByText(/GoTrue|AuthApiError|Invalid login credentials/i),
    ).not.toBeInTheDocument();
  });
});

describe("SignUpForm", () => {
  it("renders XSS in the email field as text", async () => {
    renderAuth(<SignUpForm />);
    const email = screen.getByLabelText("Email");
    fireEvent.change(email, { target: { value: XSS_FILENAME } });
    expect(email).toHaveValue(XSS_FILENAME);
    expect(screen.getByDisplayValue(XSS_FILENAME)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });
});

describe("SignInForm Google omission", () => {
  it("does not render a Google button while the provider is disabled", () => {
    renderAuth(<SignInForm />);
    expect(
      screen.queryByRole("button", { name: /google/i }),
    ).not.toBeInTheDocument();
    expect(signInWithOAuth).not.toHaveBeenCalled();
  });
});

describe("Auth omits unsupported recovery and bootstrap chrome", () => {
  it("has no recovery-code input that submits", () => {
    renderAuth(<SignInForm />);
    expect(screen.queryByRole("heading", { name: "Unavailable" })).toBeNull();
    expect(screen.queryByLabelText(/recovery/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /recover/i })).toBeNull();
  });

  it("has no owner-bootstrap form", () => {
    renderAuth(<SignInForm />);
    expect(screen.queryByText(OWNER_BOOTSTRAP_UNAVAILABLE)).toBeNull();
    expect(screen.queryByLabelText(/company/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /bootstrap|create company/i })).toBeNull();
  });
});

describe("SignInForm redirect", () => {
  it("replaces to / after a successful password sign-in", async () => {
    replace.mockClear();
    refresh.mockClear();
    signInWithPassword.mockResolvedValueOnce({
      error: null,
      data: { session: { access_token: "jwt-token" } },
    });
    const user = userEvent.setup();
    renderAuth(<SignInForm />);
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("shows handshake-safe callback copy without leaking the code", () => {
    renderAuth(<SignInForm callbackError />);
    expect(screen.getByRole("alert")).toHaveTextContent(CALLBACK_FAILED);
    expect(screen.queryByText(/pkce|code_verifier/i)).toBeNull();
  });
});

describe("ForgotPasswordForm", () => {
  it("always shows check-inbox copy and uses the PKCE recovery callback", async () => {
    resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
    const user = userEvent.setup();
    renderAuth(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(RESET_EMAIL_SENT)).toBeInTheDocument();
    expect(resetPasswordForEmail).toHaveBeenCalledWith(
      "user@example.com",
      expect.objectContaining({
        redirectTo: expect.stringMatching(/\/auth\/callback\?next=\/auth\/reset$/),
      }),
    );
  });
});

describe("ResetPasswordForm", () => {
  it("shows generic failure copy without provider traces", async () => {
    updateUser.mockResolvedValueOnce({
      error: { message: "AuthApiError: Password should be at least 6 characters" },
      data: { user: null },
    });
    const user = userEvent.setup();
    renderAuth(<ResetPasswordForm />);
    await user.type(screen.getByLabelText("New password"), "short");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(SIGN_IN_FAILED);
    expect(screen.queryByText(/AuthApiError|6 characters/i)).not.toBeInTheDocument();
  });
});

describe("InvitationAcceptForm", () => {
  it("asks the caller to sign in before posting a token", async () => {
    renderAuth(<InvitationAcceptForm />);
    expect(
      await screen.findByText("Sign in, then paste the invitation token."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept invitation" })).toBeDisabled();
  });

  it("posts { token } only and renders the accepted invitation id", async () => {
    getSession.mockResolvedValue({
      data: {
        session: {
          access_token: "jwt-token",
          user: { email: "member@example.com" },
        },
      },
    });
    acceptInvitation.mockResolvedValue({ invitation_id: "inv-1" });
    const user = userEvent.setup();
    renderAuth(<InvitationAcceptForm />);
    expect(await screen.findByText(/Signed in as/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Invitation token"), "token-ok-1");
    await user.click(screen.getByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByText(/inv-1/)).toBeInTheDocument();
    expect(acceptInvitation).toHaveBeenCalledWith({ accessToken: "jwt-token" }, "token-ok-1");
  });
});

describe("EnvMissingBanner", () => {
  it("renders when public Supabase config is absent", () => {
    envState.present = false;
    renderAuth(<EnvMissingBanner />);
    expect(
      screen.getByText("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY."),
    ).toBeInTheDocument();
  });

  it("does not move keyboard focus on first paint", async () => {
    envState.present = false;
    renderAuth(<EnvMissingBanner />);
    const banner = screen.getByRole("alert");
    await waitFor(() => {
      expect(banner).not.toHaveFocus();
    });
  });
});

describe("HandshakeBanner", () => {
  it("blocks spend when the client is below min_client_version", async () => {
    fetchMeta.mockResolvedValue({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "9.0.0",
    });
    renderAuth(<HandshakeBanner />);
    expect(await screen.findByRole("alert")).toHaveTextContent(handshakeBelowMinCopy());
  });

  it("warns when meta is unreachable", async () => {
    fetchMeta.mockRejectedValue(new Error("meta_down"));
    renderAuth(<HandshakeBanner />);
    expect(
      await screen.findByText(/Compatibility could not be confirmed/),
    ).toBeInTheDocument();
  });
});
