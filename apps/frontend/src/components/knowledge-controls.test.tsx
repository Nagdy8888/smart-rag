// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentGovernancePanel } from "./documents/document-governance";
import { DocumentScope } from "./chat/document-scope";
import { KnowledgePanel } from "./admin/knowledge-panel";

const api = vi.hoisted(() => ({ governance: vi.fn(), versions: vi.fn(), scope: vi.fn(), list: vi.fn(), update: vi.fn(), users: vi.fn(), docs: vi.fn() }));
vi.mock("../lib/auth/use-api-auth", () => ({ useApiAuth: () => ({ accessToken: "fixture" }) }));
vi.mock("../lib/api/document-governance", () => ({ documentGovernance: api.governance, governanceVersions: api.versions }));
vi.mock("../lib/api/knowledge-scope", () => ({ knowledgeScope: api.scope }));
vi.mock("../lib/api/knowledge-maintenance", () => ({ listMaintenance: api.list, updateMaintenance: api.update }));
vi.mock("../lib/api", () => ({ listWorkspaceUsers: api.users, listDocuments: api.docs, nextDocumentCursor: () => null, createConversation: vi.fn() }));

const id = "11111111-1111-4111-8111-111111111111";
const governance = { version_id: id, version_number: 1, owner_user_id: id, knowledge_area: "HR", review_due_at: null,
  authority_status: "unreviewed", effective_at: null, superseded_by_version_id: null, governance_generation: 1, reliability_enabled: true };
const clients: QueryClient[] = [];
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  api.governance.mockResolvedValue(governance);
  api.versions.mockResolvedValue([governance]);
  api.users.mockResolvedValue({ members: [{ user_id: id, display_name: "Reviewer", email: "reviewer@example.test", role: "owner", disabled_at: null }], pending_invitations: [] });
  api.docs.mockResolvedValue([{ document_id: id, title: "Handbook", current_version_id: id, created_at: "2026-10-01T00:00:00Z" }]);
  api.update.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); });

describe("knowledge controls", () => {
  it("submits explicit approval metadata with the current optimistic revision", async () => {
    const user = userEvent.setup();
    mount(<DocumentGovernancePanel documentId={id} currentVersionId={id} canManage />);
    await screen.findByText("Manage authority");
    await user.click(screen.getByText("Manage authority"));
    await screen.findByRole("option", { name: "Reviewer" });
    await user.selectOptions(screen.getByLabelText("Authority status"), "approved");
    await user.type(screen.getByLabelText("Effective date (UTC)"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Save authority" }));
    await waitFor(() => expect(api.governance).toHaveBeenCalledWith({ accessToken: "fixture" }, id,
      expect.objectContaining({ authority_status: "approved", version_id: id, expected_generation: 1, effective_at: "2026-10-01T00:00:00Z" })));
  });

  it("clears a saved document scope explicitly instead of silently broadening it", async () => {
    const user = userEvent.setup(); const selected = vi.fn();
    api.scope.mockResolvedValue({ document_id: id, title: "Handbook", unavailable: false, enabled: true });
    mount(<DocumentScope conversationId={id} onConversationId={selected} running={false} onPendingChange={vi.fn()} />);
    await screen.findByRole("button", { name: "Clear document scope" });
    await user.click(screen.getByRole("button", { name: "Clear document scope" }));
    await waitFor(() => expect(api.scope).toHaveBeenCalledWith({ accessToken: "fixture" }, id, null));
    expect(selected).toHaveBeenCalledWith(id);
  });

  it("requires a human reason and preserves the revision when resolving a report", async () => {
    const user = userEvent.setup();
    api.list.mockResolvedValue([{ kind: "feedback", source_id: id, document_id: null, run_id: id,
      title: "outdated answer", report: {}, status: "open", assigned_to: null, reason: null, revision: 0 }]);
    mount(<KnowledgePanel />);
    await screen.findByRole("button", { name: "Save review" });
    await user.selectOptions(screen.getByLabelText("Review status"), "resolved");
    await user.click(screen.getByRole("button", { name: "Save review" }));
    expect(api.update).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Review reason or expected correction"), "Approved the current policy");
    await user.click(screen.getByRole("button", { name: "Save review" }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith({ accessToken: "fixture" }, expect.anything(),
      expect.objectContaining({ expected_revision: 0, status: "resolved", reason: "Approved the current policy" })));
  });
});
