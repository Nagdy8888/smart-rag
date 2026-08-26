/**
 * Hydration-stable boolean layout preference backed by localStorage.
 */

"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  readBooleanPreference,
  writeBooleanPreference,
} from "../layout-preferences";

/**
 * Subscribe to same-tab custom events and cross-tab `storage` events.
 *
 * @param key - Storage key.
 * @param onStoreChange - React store listener.
 * @returns Unsubscribe function.
 */
function subscribePreference(key: string, onStoreChange: () => void): () => void {
  /**
   * Notify React when this key changes.
   *
   * @param event - Browser storage or custom preference event.
   */
  function handleEvent(event: Event): void {
    if (event instanceof StorageEvent && event.key !== null && event.key !== key) {
      return;
    }
    onStoreChange();
  }
  window.addEventListener("storage", handleEvent);
  window.addEventListener(preferenceEventName(key), handleEvent);
  return () => {
    window.removeEventListener("storage", handleEvent);
    window.removeEventListener(preferenceEventName(key), handleEvent);
  };
}

/**
 * Custom-event name for same-tab preference writes.
 *
 * @param key - Storage key.
 * @returns Event type.
 */
export function preferenceEventName(key: string): string {
  return `smart-rag.layout-preference:${key}`;
}

/**
 * Read and write one boolean layout preference.
 *
 * The server snapshot and first client snapshot use `fallback`. Persisted
 * values apply after hydration. Auth/session data is never stored here.
 *
 * @param key - Storage key from `layout-preferences.ts`.
 * @param fallback - Hydration-stable default.
 * @returns Current value and a setter that persists and notifies.
 */
export function useLayoutPreference(
  key: string,
  fallback: boolean,
): [boolean, (next: boolean) => void] {
  const value = useSyncExternalStore(
    (onStoreChange) => subscribePreference(key, onStoreChange),
    () => readBooleanPreference(key, fallback),
    () => fallback,
  );

  const setValue = useCallback(
    (next: boolean) => {
      writeBooleanPreference(key, next);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(preferenceEventName(key)));
      }
    },
    [key],
  );

  return [value, setValue];
}
