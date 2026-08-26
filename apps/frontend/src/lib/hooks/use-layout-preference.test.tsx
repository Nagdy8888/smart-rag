// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NAV_EXPANDED_STORAGE_KEY } from "../layout-preferences";
import { useLayoutPreference } from "./use-layout-preference";

describe("useLayoutPreference", () => {
  it("uses the fallback until a same-tab write notifies subscribers", () => {
    window.localStorage.removeItem(NAV_EXPANDED_STORAGE_KEY);
    const { result } = renderHook(() =>
      useLayoutPreference(NAV_EXPANDED_STORAGE_KEY, true),
    );
    expect(result.current[0]).toBe(true);
    act(() => {
      result.current[1](false);
    });
    expect(result.current[0]).toBe(false);
    expect(window.localStorage.getItem(NAV_EXPANDED_STORAGE_KEY)).toBe("false");
  });
});
