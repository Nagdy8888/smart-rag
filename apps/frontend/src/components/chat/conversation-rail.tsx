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
import { UserText } from "../ui/user-text";
import styles from "./chat.module.css";

export type ConversationRailProps = {
  /** Loaded conversations. One API page only. */
  conversations: ConversationResponse[];
  /** Selected conversation id. */
  selectedId: string | null;
  /** True while the list query is pending. */
  loading: boolean;
  /** Create a conversation. */
  onCreate: () => void;
  /** Select a conversation. */
  onSelect: (conversation: ConversationResponse) => void;
  /** Delete the selected conversation after the row menu. */
  onDelete: () => void;
};

/**
 * Render the conversation rail.
 *
 * @param props - Controlled list data and callbacks.
 * @returns Aside. Mutations stay in ChatApp.
 */
export function ConversationRail({
  conversations,
  selectedId,
  loading,
  onCreate,
  onSelect,
  onDelete,
}: ConversationRailProps) {
  return (
    <aside className={styles.rail} aria-label="Conversations">
      <div className={styles.railHeader}>
        <h2 className={styles.railTitle}>Conversations</h2>
        <div className={styles.row}>
          <Button type="button" variant="secondary" onClick={onCreate}>
            New conversation
          </Button>
          <Menu
            label="Conversation actions"
            trigger={<Icon name="more" />}
            items={[
              {
                id: "delete",
                label: "Delete conversation",
                danger: true,
                disabled: selectedId === null,
                onSelect: onDelete,
              },
            ]}
          />
        </div>
      </div>
      {loading ? <Skeleton label="Loading conversations" width="100%" /> : null}
      {conversations.length === 0 && !loading ? (
        <EmptyState title="No conversations yet">
          Start a conversation to ask across authorized documents.
        </EmptyState>
      ) : null}
      <RovingList
        aria-label="Conversations"
        selectedId={selectedId}
        items={conversations.map((item) => ({
          id: item.conversation_id,
          item,
        }))}
        onSelect={onSelect}
      >
        {(item) => (
          <span className={styles.conversationButton}>
            <UserText value={item.title ?? item.conversation_id} />
          </span>
        )}
      </RovingList>
    </aside>
  );
}
