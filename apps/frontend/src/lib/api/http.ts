/**
 * URL join and bounded JSON object reads. No domain endpoints.
 */

import { apiBaseUrl } from "../env";

/**
 * Join API origin and a path that may already be absolute-path.
 *
 * @param path - `/conversations` or a `stream_path`.
 * @returns Absolute URL.
 */
export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const prefix = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseUrl()}${prefix}`;
}

/**
 * Parse a JSON object body, or `{}` when the payload is missing or not a map.
 *
 * @param response - Fetch response.
 * @returns Object map. Arrays and primitives become `{}`.
 */
export async function readJsonObject(
  response: Response,
): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = await response.json();
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}
