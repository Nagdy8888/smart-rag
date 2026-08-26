/**
 * Conversation list rail. Controlled by ChatApp.
 */

"use client";

import { memo } from "react";
import type { ConversationResponse } from "../../lib/types";
import { conversationAgeGroup, formatRelativeTime } from "../../lib/relative-time";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { Menu } from "../ui/menu";
import { RovingList } from "../ui/roving-list";
import { Skeleton } from "../ui/skeleton";
import { UserText } from "../ui/user-text";
import styles from "./chat.module.css";

/** Incremented on each memoized rail render. Used by isolation tests. */
export const conversationRailRenderCount = { value: 0 };

export type ConversationRailProps = {
  /** Loaded conversations. One API page only. */
  conversations: ConversationResponse[];
  /** Selected conversation id. */
  selectedId: string | null;
  /** True while the list query is pending. */
  loading: boolean;
  /** Start a local blank session. First Send creates the row. */
  onCreate: () => void;
  /** Select a conversation. */
  onSelect: (conversation: ConversationResponse) => void;
  /** Delete one conversation after the row menu or hover control. */
  onDelete: (conversationId: string) => void;
  /** True while a delete mutation is in flight. */
  deletePending?: boolean;
  /** Desktop expanded Sessions column. */
  expanded?: boolean;
  /** Toggle the desktop Sessions column. */
  onToggleExpanded?: () => void;
  /** Show the desktop collapse control. Hidden in the mobile sheet. */
  showCollapseToggle?: boolean;
};

/**
 * Visible title for a session row. Never the conversation UUID.
 *
 * @param title - API title, possibly null.
 * @returns Title or `Untitled chat`.
 */
export function conversationDisplayTitle(title: string | null): string {
  return title === null || title.trim() === "" ? "Untitled chat" : title;
}

/**
 * Render the conversation rail.
 *
 * @param props - Controlled list data and callbacks.
 * @returns Aside whose session list scrolls independently of the header.
 * @remarks
 * Render-isolation contract: ChatApp must pass stable callbacks and must
 * not derive rail props from SSE `chat` view state. Memoization holds
 * only when conversation-list data is unchanged.
 */
export const ConversationRail = memo(function ConversationRail({
  conversations,
  selectedId,
  loading,
  onCreate,
  onSelect,
  onDelete,
  deletePending = false,
  expanded = true,
  onToggleExpanded,
  showCollapseToggle = false,
}: ConversationRailProps) {
  conversationRailRenderCount.value += 1;

  return (
    <aside
      className={[styles.rail, expanded ? undefined : styles.railIsCollapsed]
        .filter(Boolean)
        .join(" ")}
      aria-label="Sessions"
      data-testid="sessions-rail"
      data-expanded={expanded ? "true" : "false"}
    >
      {!expanded && showCollapseToggle && onToggleExpanded ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={styles.railCollapse}
          aria-expanded={false}
          aria-label="Expand sessions"
          data-action-id="ask.sessions_toggle"
          onClick={onToggleExpanded}
        >
          <Icon name="panelExpand" />
        </Button>
      ) : null}
      <div hidden={!expanded} className={styles.railBody}>
        <div className={styles.railHeader}>
          <h2 className={styles.railTitle}>Sessions</h2>
          <div className={styles.railActions}>
            {showCollapseToggle && onToggleExpanded ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className={styles.railCollapse}
                aria-expanded={expanded}
                aria-label="Collapse sessions"
                data-action-id="ask.sessions_toggle"
                onClick={onToggleExpanded}
              >
                <Icon name="panelCollapse" />
              </Button>
            ) : null}
            <Button
              type="button"
              variant="primary"
              size="compact"
              data-action-id="ask.new_session"
              aria-label="New chat"
              onClick={onCreate}
            >
              <Icon name="plus" />
            </Button>
            <Menu
              label="Conversation actions"
              trigger={<Icon name="more" />}
              items={[
                {
                  id: "delete",
                  label: deletePending ? "Deleting…" : "Delete",
                  danger: true,
                  actionId: "ask.delete_session",
                  disabled: selectedId === null || deletePending,
                  onSelect: () => {
                    if (selectedId !== null) {
                      onDelete(selectedId);
                    }
                  },
                },
              ]}
            />
          </div>
        </div>
        {loading ? <Skeleton label="Loading conversations" width="100%" /> : null}
        {conversations.length === 0 && !loading ? (
          <EmptyState title="No sessions yet" body="Ask a question to create one." />
        ) : null}
        <RovingList
          className={styles.railList}
          aria-label="Sessions"
          selectedId={selectedId}
          items={conversations.map((item) => ({
            id: item.conversation_id,
            item,
          }))}
          onSelect={onSelect}
          getAccessibleName={(item) => conversationDisplayTitle(item.title)}
          getGroupLabel={(item, previous) => {
            const group = conversationAgeGroup(item.created_at);
            if (previous === null) {
              return group;
            }
            return conversationAgeGroup(previous.created_at) === group
              ? null
              : group;
          }}
          groupClassName={styles.railGroupLabel}
        >
          {(item) => (
            <div className={styles.conversationButton}>
              <div className={styles.conversationCopy}>
                <div className={styles.conversationTitle}>
                  <UserText value={conversationDisplayTitle(item.title)} />
                </div>
                {item.created_at ? (
                  <div className={styles.conversationTime} aria-hidden="true">
                    {formatRelativeTime(item.created_at)}
                  </div>
                ) : null}
              </div>
              <div className={styles.conversationDelete}>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Delete conversation"
                  pending={deletePending && selectedId === item.conversation_id}
                  pendingLabel="Deleting…"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(item.conversation_id);
                  }}
                >
                  <Icon name="trash" />
                </Button>
              </div>
            </div>
          )}
        </RovingList>
      </div>
    </aside>
  );
});
