/**
 * Document-scoped chrome for `/tables?documentId=`.
 */

"use client";

import Link from "next/link";
import { UserText } from "../ui/user-text";
import styles from "./tables.module.css";

export type TablesDocumentBarProps = {
  /** Seeded `?documentId=`. */
  documentId: string;
  /** Title from `GET /documents/{id}`, or the id when the title is missing. */
  documentName: string;
};

/**
 * Link back to the source document and clear the tables seed.
 *
 * @param props - Seeded document id and display name.
 * @returns Context row. Does not fetch.
 */
export function TablesDocumentBar({
  documentId,
  documentName,
}: TablesDocumentBarProps) {
  return (
    <div className={styles.contextBar}>
      <p className={styles.backLink}>
        <Link href={`/documents/${encodeURIComponent(documentId)}`}>
          Back to document
        </Link>
      </p>
      <p className={styles.contextTitle}>
        Tables in <UserText value={documentName} />
      </p>
      <p className={styles.backLink}>
        <Link href="/tables">All tables</Link>
      </p>
    </div>
  );
}
