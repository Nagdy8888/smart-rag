/**
 * Client handshake version sent on new paid POST bodies.
 *
 * Must be semver-like and ≥ FastAPI `MIN_CLIENT_VERSION` (default `0.1.0`).
 * Resume GET does not send this header.
 */

/** Semver-like client pin published on `X-Client-Version`. */
export const CLIENT_VERSION = "0.1.0";

/**
 * SSE catalog label this UI understands. Newer `sse_schema_version` values
 * are additive: unknown events are ignored and paid work may continue.
 */
export const CLIENT_SSE_SCHEMA_VERSION = "1";

const SEMVER = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/;

/**
 * Parse a `major.minor.patch` string into a comparable triple.
 *
 * @param value - Client or published minimum version.
 * @returns Integer triple, or null when the value is not comparable.
 */
export function parseSemverTuple(value: string): [number, number, number] | null {
  const match = SEMVER.exec(value.trim());
  if (match === null) {
    return null;
  }
  return [
    Number.parseInt(match[1] ?? "", 10),
    Number.parseInt(match[2] ?? "", 10),
    Number.parseInt(match[3] ?? "", 10),
  ];
}

/**
 * Return whether `clientVersion` meets `minimum`, matching FastAPI
 * `client_version_is_supported`.
 *
 * Missing, empty, or unparsable versions are unsupported.
 *
 * @param clientVersion - `X-Client-Version` / `CLIENT_VERSION`.
 * @param minimum - `GET /api/meta` `min_client_version`.
 * @returns True only when both parse and client ≥ minimum.
 */
export function clientVersionIsSupported(
  clientVersion: string | null | undefined,
  minimum: string,
): boolean {
  if (clientVersion === null || clientVersion === undefined || clientVersion.trim() === "") {
    return false;
  }
  const parsed = parseSemverTuple(clientVersion);
  const minimumParsed = parseSemverTuple(minimum);
  if (parsed === null || minimumParsed === null) {
    return false;
  }
  if (parsed[0] !== minimumParsed[0]) {
    return parsed[0] > minimumParsed[0];
  }
  if (parsed[1] !== minimumParsed[1]) {
    return parsed[1] > minimumParsed[1];
  }
  return parsed[2] >= minimumParsed[2];
}

/**
 * Return whether this client is strictly below the published minimum.
 *
 * @param clientVersion - Local pin.
 * @param minimum - Published `min_client_version`.
 * @returns True when a comparable client is below minimum.
 */
export function isClientBelowMinimum(clientVersion: string, minimum: string): boolean {
  return !clientVersionIsSupported(clientVersion, minimum);
}
