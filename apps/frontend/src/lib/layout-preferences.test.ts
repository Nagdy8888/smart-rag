// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";
import {
  NAV_EXPANDED_STORAGE_KEY,
  readBooleanPreference,
  writeBooleanPreference,
} from "./layout-preferences";

afterEach(() => {
  window.localStorage.clear();
});

describe("layout preferences", () => {
  it("returns the fallback when unset", () => {
    expect(readBooleanPreference(NAV_EXPANDED_STORAGE_KEY, true)).toBe(true);
    expect(readBooleanPreference(NAV_EXPANDED_STORAGE_KEY, false)).toBe(false);
  });

  it("round-trips a stored boolean", () => {
    writeBooleanPreference(NAV_EXPANDED_STORAGE_KEY, false);
    expect(readBooleanPreference(NAV_EXPANDED_STORAGE_KEY, true)).toBe(false);
  });
});
