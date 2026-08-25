/**
 * Conversation list rail. Controlled by ChatApp.
 */

"use client";

import type { ConversationResponse } from "../../lib/types";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { Menu } from "../ui/menu";
import { RovingList } from "../ui/roving-list";
import { Skeleton } from "../ui/skeleton";
import { Tooltip } from "../ui/tooltip";
import { UserText } from "../ui/user-text";
import styles from "./chat.module.css";

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
  /** Delete the selected conversation after the row menu. */
  onDelete: () => void;
  /** Desktop expanded Sessions column. */
  expanded?: boolean;
  /** Toggle the desktop Sessions column. */
  onToggleExpanded?: () => void;
  /** Show the desktop collapse control. Hidden in the mobile sheet. */
  showCollapseToggle?: boolean;
};

/**
 * Render the conversation rail.
 *
 * @param props - Controlled list data and callbacks.
 * @returns Aside whose session list scrolls independently of the header.
 * @remarks Mutations stay in ChatApp. The header stays outside the list
 *   scrollport so New and Delete remain visible.
 */
export function ConversationRail({
  conversations,
  selectedId,
  loading,
  onCreate,
  onSelect,
  onDelete,
  expanded = true,
  onToggleExpanded,
  showCollapseToggle = false,
}: ConversationRailProps) {
  const toggleLabel = expanded ? "Collapse sessions" : "Expand sessions";
  return (
    <aside
      className={styles.rail}
      aria-label="Sessions"
      data-expanded={expanded ? "true" : "false"}
    >
      <div className={styles.railHeader}>
        {showCollapseToggle && onToggleExpanded ? (
          <Tooltip text={toggleLabel}>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={toggleLabel}
              aria-expanded={expanded}
              data-action-id="ask.sessions_toggle"
              onClick={onToggleExpanded}
            >
              <Icon name={expanded ? "panelCollapse" : "panelExpand"} />
            </Button>
          </Tooltip>
        ) : null}
        <h2 className={styles.railTitle}>Sessions</h2>
        <div className={styles.railActions}>
          <Button type="button" variant="primary" data-action-id="ask.new_session" onClick={onCreate}>
            New
          </Button>
          <Menu
            label="Conversation actions"
            trigger={<Icon name="more" />}
            items={[
              {
                id: "delete",
                label: "Delete",
                danger: true,
                actionId: "ask.delete_session",
                disabled: selectedId === null,
                onSelect: onDelete,
              },
            ]}
          />
        </div>
      </div>
      {expanded ? (
        <>
          {loading ? <Skeleton label="Loading conversations" width="100%" /> : null}
          {conversations.length === 0 && !loading ? (
            <EmptyState title="No sessions yet. Ask a question to create one.">
              Earlier messages are not loaded in this client.
            </EmptyState>
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
          >
            {(item) => (
              <span className={styles.conversationButton}>
                <span className={styles.conversationTitle}>
                  <UserText value={item.title ?? item.conversation_id} />
                </span>
                {item.created_at ? (
                  <span className={styles.muted} aria-hidden="true">
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                ) : null}
              </span>
            )}
          </RovingList>
        </>
      ) : null}
    </aside>
  );
}
