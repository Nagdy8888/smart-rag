// @vitest-environment jsdom
import { renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ConversationMessage } from "../../../lib/types";
import { useRestoreHistoryScope } from "./use-restore-history-scope";

it("restores recorded scopes when switching histories without overwriting later edits", () => {
  const restore = vi.fn();
  const web: ConversationMessage = { message_id: "m", role: "user", content: "Question",
    created_at: "2026-10-28T00:00:00Z", requested_search_scope: "web" };
  const { rerender } = renderHook(({ id, messages }) => useRestoreHistoryScope(id, false, messages, null, restore),
    { initialProps: { id: "web-conversation", messages: [web] } });
  expect(restore).toHaveBeenLastCalledWith("web-conversation", "web");
  rerender({ id: "web-conversation", messages: [{ ...web, content: "Refetched" }] });
  expect(restore).toHaveBeenCalledTimes(1);
  rerender({ id: "general-conversation", messages: [{ ...web, requested_search_scope: "general_knowledge" }] });
  expect(restore).toHaveBeenLastCalledWith("general-conversation", "general_knowledge");
  rerender({ id: "web-conversation", messages: [web] });
  expect(restore).toHaveBeenLastCalledWith("web-conversation", "web");
});
