// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { XSS_FILENAME } from "../../lib/hostile-text-fixtures";
import { SIGN_IN_FAILED } from "../../lib/auth/copy";
import { SessionProvider } from "../../lib/auth/session-provider";
import { SignInForm, SignUpForm } from "./auth-screens";
import { OWNER_BOOTSTRAP_UNAVAILABLE } from "../../lib/auth/copy";

afterEach(() => {
  cleanup();
});

const signInWithPassword = vi.fn();
const signInWithOAuth = vi.fn();
const signUp = vi.fn();
const getSession = vi.fn(async () => ({ data: { session: null } }));
const onAuthStateChange = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));

vi.mock("../../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      signInWithPassword,
      signInWithOAuth,
      signUp,
      getSession,
      onAuthStateChange,
      signOut: vi.fn(),
    },
  }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchMeta: vi.fn(async () => ({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "0.1.0",
    })),
    fetchReady: vi.fn(async () => null),
  };
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
