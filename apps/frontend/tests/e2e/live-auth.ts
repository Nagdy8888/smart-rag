/**
 * Live GoTrue/FastAPI helpers for Playwright. Skip when the stack is down.
 * Creates a confirmed local user through GoTrue admin; no `X-Test-*` bypass.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const LOCAL_FASTAPI = "http://127.0.0.1:8000";
const LIVE_PASSWORD = "Phase8Live9x";

/**
 * Walk parents until `pnpm-workspace.yaml` is found.
 *
 * @param start - Directory to start from.
 * @returns Repository root, or null.
 */
function findRepoRoot(start: string): string | null {
  let dir = path.resolve(start);
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(path.join(dir, "pnpm-workspace.yaml"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      return null;
    }
    dir = parent;
  }
  return null;
}

/**
 * Read local CLI status keys without printing credential values.
 *
 * @returns Status map, or null when the pinned CLI is down.
 */
function readLocalSupabaseStatus(): Record<string, string> | null {
  const root = findRepoRoot(process.cwd());
  if (root === null) {
    return null;
  }
  const binName = process.platform === "win32" ? "supabase.cmd" : "supabase";
  const bin = path.join(root, "node_modules", ".bin", binName);
  if (!existsSync(bin)) {
    return null;
  }
  const result = spawnSync(bin, ["status", "-o", "json"], {
    cwd: root,
    encoding: "utf8",
    timeout: 30_000,
    shell: process.platform === "win32",
    windowsHide: true,
  });
  if (result.status !== 0) {
    return null;
  }
  const stdout = result.stdout ?? "";
  const start = stdout.indexOf("{");
  const end = stdout.lastIndexOf("}");
  if (start < 0 || end <= start) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(stdout.slice(start, end + 1));
    if (parsed === null || typeof parsed !== "object") {
      return null;
    }
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === "string") {
        out[key] = value;
      }
    }
    if (!out.API_URL || !out.SERVICE_ROLE_KEY) {
      return null;
    }
    return out;
  } catch {
    return null;
  }
}

/**
 * Fetch live FastAPI readiness, or null when the API is down.
 *
 * @param request - Playwright API request fixture.
 * @returns JSON body, or null.
 */
export async function fetchLocalReady(
  request: APIRequestContext,
): Promise<Record<string, unknown> | null> {
  try {
    const response = await request.get(`${LOCAL_FASTAPI}/health/ready`, {
      timeout: 3000,
    });
    if (!response.ok()) {
      return null;
    }
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Create a confirmed local Auth user and sign in through the login form.
 *
 * @param page - Playwright page.
 * @param request - Playwright API request fixture.
 * @returns Nothing. Skips when FastAPI or GoTrue is down.
 */
export async function signInLiveMember(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  const ready = await fetchLocalReady(request);
  if (ready === null) {
    test.skip(true, "local FastAPI is unreachable at 127.0.0.1:8000");
    return;
  }
  const status = readLocalSupabaseStatus();
  if (status === null) {
    test.skip(true, "local Supabase CLI status is unavailable");
    return;
  }
  const authOrigin = status.API_URL.replace(/\/$/, "");
  const email = `phase8-pw-${Date.now()}@example.com`;
  const created = await request.post(`${authOrigin}/auth/v1/admin/users`, {
    headers: {
      Authorization: `Bearer ${status.SERVICE_ROLE_KEY}`,
      apikey: status.SERVICE_ROLE_KEY,
      "Content-Type": "application/json",
    },
    data: {
      email,
      password: LIVE_PASSWORD,
      email_confirm: true,
    },
  });
  if (created.status() >= 400) {
    test.skip(true, `local Auth admin create failed (${created.status()})`);
    return;
  }
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(LIVE_PASSWORD);
  const tokenOk = page.waitForResponse(
    (response) => response.url().includes("/auth/v1/token") && response.ok(),
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  await tokenOk;
  await page.goto("/");
  await expect(page).not.toHaveURL(/\/login/);
}
