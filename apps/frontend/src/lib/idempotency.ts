/**
 * Stable mutation keys. One key is reused across a single retry attempt.
 */

/**
 * Return a new UUID v4 idempotency key.
 *
 * Callers must keep the returned value for the lifetime of one paid attempt,
 * including retries of that attempt. Do not call this inside a retry loop.
 *
 * @returns RFC 4122 UUID string.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
