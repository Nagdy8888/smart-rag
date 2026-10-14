/**
 * Scrub browser errors before they leave the page for GlitchTip.
 */

const FORBIDDEN_KEYS = new Set([
  "api_key",
  "authorization",
  "cookie",
  "cookies",
  "email",
  "html",
  "page_content",
  "passage",
  "password",
  "prompt",
  "query",
  "retrieved_text",
  "secret",
  "snippet",
  "source",
  "token",
]);

/** Fields the scrubber is allowed to change. */
export type BrowserErrorEvent = {
  message?: string;
  request?: {
    cookies?: unknown;
    headers?: unknown;
    data?: unknown;
  };
  extra?: Record<string, unknown>;
  exception?: {
    values?: Array<{ value?: string }>;
  };
};

/**
 * Replace bearer tokens and provider-key shapes, then cap length.
 *
 * @param value - Exception or event text.
 * @returns Redacted text no longer than 2048 characters.
 */
export function redactBrowserText(value: string): string {
  const redacted = value
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, "[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [REDACTED]");
  return redacted.length > 2048 ? `${redacted.slice(0, 2048)}...[TRUNCATED]` : redacted;
}

/**
 * Drop request bodies and passage-like keys from one browser error.
 *
 * @param event - SDK event about to be sent. Mutated in place.
 * @returns The same event after scrubbing.
 */
export function scrubBrowserErrorEvent<T extends BrowserErrorEvent>(event: T): T {
  if (event.request) {
    delete event.request.cookies;
    delete event.request.headers;
    delete event.request.data;
  }
  if (typeof event.message === "string") {
    event.message = redactBrowserText(event.message);
  }
  for (const value of event.exception?.values ?? []) {
    if (typeof value.value === "string") {
      value.value = redactBrowserText(value.value);
    }
  }
  if (event.extra) {
    for (const key of Object.keys(event.extra)) {
      if (FORBIDDEN_KEYS.has(key.toLowerCase())) {
        delete event.extra[key];
      }
    }
  }
  return event;
}
