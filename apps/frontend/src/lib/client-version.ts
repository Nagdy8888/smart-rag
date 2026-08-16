/**
 * Client handshake version sent on new paid POST bodies.
 *
 * Must be semver-like and ≥ FastAPI `MIN_CLIENT_VERSION` (default `0.1.0`).
 * Resume GET does not send this header.
 */
export const CLIENT_VERSION = "0.1.0";
