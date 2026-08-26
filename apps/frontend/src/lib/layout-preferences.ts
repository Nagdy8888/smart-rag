/**
 * Persist Ask/shell expand-collapse choices in localStorage.
 */

export const NAV_EXPANDED_STORAGE_KEY = "smart-rag.nav-expanded";
export const SESSIONS_EXPANDED_STORAGE_KEY = "smart-rag.sessions-expanded";

/**
 * Default desktop nav to expanded at the 1280px multi-pane breakpoint.
 *
 * @returns True when the viewport is wide or matchMedia is unavailable.
 */
export function defaultNavExpanded(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return true;
  }
  return window.matchMedia("(min-width: 1280px)").matches;
}

/**
 * Read a boolean preference, or the fallback when unset or unavailable.
 *
 * @param key - Storage key.
 * @param fallback - Value when the key is missing or storage is unavailable.
 * @returns Stored boolean, or fallback.
 */
export function readBooleanPreference(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") {
    return fallback;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "true") {
      return true;
    }
    if (raw === "false") {
      return false;
    }
  } catch {
    return fallback;
  }
  return fallback;
}

/**
 * Store a boolean preference.
 *
 * @param key - Storage key.
 * @param value - Value to persist.
 */
export function writeBooleanPreference(key: string, value: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, value ? "true" : "false");
  } catch {
    return;
  }
}
