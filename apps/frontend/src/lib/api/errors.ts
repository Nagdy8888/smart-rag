/**
 * Classified FastAPI failures and throw helpers. No fetch calls.
 */

export type HandshakeFailure = {
  kind: "upgrade";
  minClientVersion: string;
  sseSchemaVersion: string;
};

export type AuthFailure = {
  kind: "auth";
  status: number;
  detail: string;
};

export type FailClosedFailure = {
  kind: "fail_closed";
  status: number;
  detail: string;
};

export type BudgetFailure = {
  kind: "budget";
  detail: string;
};

export type RateFailure = {
  kind: "rate";
  detail: string;
  retryAfter: string | null;
};

export type DeletedFailure = {
  kind: "deleted";
};

export type ConflictFailure = {
  kind: "conflict";
  detail: string;
};

export type ValidationFailure = {
  kind: "validation";
  detail: string;
};

export type ProtocolFailure = {
  kind: "protocol";
  detail: string;
};

export type ServerFailure = {
  kind: "server";
  status: number;
};

export type ApiFailure =
  | HandshakeFailure
  | AuthFailure
  | FailClosedFailure
  | BudgetFailure
  | RateFailure
  | DeletedFailure
  | ConflictFailure
  | ValidationFailure
  | ProtocolFailure
  | ServerFailure;

/**
 * Typed HTTP failure thrown by chat mutations. Callers must not treat this as
 * success.
 */
export class ClassifiedApiError extends Error {
  readonly failure: ApiFailure;

  /**
   * @param failure - Classified FastAPI failure.
   */
  constructor(failure: ApiFailure) {
    super(failure.kind);
    this.name = "ClassifiedApiError";
    this.failure = failure;
  }
}

/**
 * Return whether an unknown thrown value is a classified API failure.
 *
 * @param error - Caught value.
 * @returns True when `error` is `ClassifiedApiError`.
 */
export function isClassifiedApiError(error: unknown): error is ClassifiedApiError {
  return error instanceof ClassifiedApiError;
}

/**
 * Return whether a FastAPI `detail` looks like a short code, not a trace.
 *
 * @param value - Candidate detail.
 * @returns True for `snake_case` codes at most 64 chars.
 */
export function isSafeDetailCode(value: string): boolean {
  const trimmed = value.trim();
  return /^[a-z][a-z0-9_]{0,63}$/i.test(trimmed);
}

/**
 * Read a sanitized `detail` string from a FastAPI JSON body.
 *
 * @param body - Parsed object.
 * @param fallback - Used when `detail` is missing, not a string, or a trace.
 * @returns Code-like detail. Never exception text from unknown shapes.
 *   The historical FastAPI sentence ``Session revoked`` aliases to
 *   ``session_revoked`` only.
 */
export function sanitizedDetail(
  body: Record<string, unknown>,
  fallback: string,
): string {
  if (typeof body.detail !== "string") {
    return fallback;
  }
  if (body.detail === "Session revoked" || body.detail === "session_revoked") {
    return "session_revoked";
  }
  return isSafeDetailCode(body.detail) ? body.detail : fallback;
}

/**
 * Read `Retry-After` from a Fetch Headers map or a plain record.
 *
 * @param headers - Optional response headers.
 * @returns Header value, or null.
 */
export function retryAfterHeader(
  headers?: Headers | Record<string, string>,
): string | null {
  if (headers === undefined) {
    return null;
  }
  if (headers instanceof Headers) {
    return headers.get("Retry-After");
  }
  return headers["Retry-After"] ?? headers["retry-after"] ?? null;
}

/**
 * Parse a FastAPI error body into a typed UI failure.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @param headers - Optional headers for `Retry-After` on 429.
 * @returns Typed failure when the status is an expected gate.
 */
export function classifyApiError(
  status: number,
  body: Record<string, unknown>,
  headers?: Headers | Record<string, string>,
): ApiFailure | null {
  if (status === 426) {
    const min =
      typeof body.min_client_version === "string"
        ? body.min_client_version
        : "0.1.0";
    const schema =
      typeof body.sse_schema_version === "string" ? body.sse_schema_version : "1";
    return {
      kind: "upgrade",
      minClientVersion: min,
      sseSchemaVersion: schema,
    };
  }
  if (status === 401 || status === 403) {
    return {
      kind: "auth",
      status,
      detail: sanitizedDetail(body, "unauthorized"),
    };
  }
  if (status === 402) {
    return {
      kind: "budget",
      detail: sanitizedDetail(body, "budget_exhausted"),
    };
  }
  if (status === 429) {
    return {
      kind: "rate",
      detail: sanitizedDetail(body, "rate_limited"),
      retryAfter: retryAfterHeader(headers),
    };
  }
  if (status === 503) {
    return {
      kind: "fail_closed",
      status,
      detail: sanitizedDetail(body, "limiter_unavailable"),
    };
  }
  if (status === 404) {
    return { kind: "deleted" };
  }
  if (status === 409) {
    return {
      kind: "conflict",
      detail: sanitizedDetail(body, "conflict"),
    };
  }
  if (status === 422) {
    return {
      kind: "validation",
      detail: sanitizedDetail(body, "validation_error"),
    };
  }
  if (status >= 500) {
    return { kind: "server", status };
  }
  return null;
}

/**
 * Map a non-OK response to a typed failure, using generic copy for unknowns.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @param headers - Optional headers for `Retry-After`.
 * @returns Never null when the caller already knows the response failed.
 */
export function classifiedOrGenericFailure(
  status: number,
  body: Record<string, unknown>,
  headers?: Headers | Record<string, string>,
): ApiFailure {
  return classifyApiError(status, body, headers) ?? { kind: "server", status };
}

/**
 * Throw a classified error when a mutation or fetch is not successful.
 *
 * @param response - Fetch response.
 * @param body - Parsed JSON object, or empty.
 * @throws ClassifiedApiError
 */
export function throwIfNotOk(
  response: Response,
  body: Record<string, unknown>,
): void {
  if (response.ok) {
    return;
  }
  throw new ClassifiedApiError(
    classifiedOrGenericFailure(response.status, body, response.headers),
  );
}
