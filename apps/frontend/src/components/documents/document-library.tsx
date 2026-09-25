/**
 * Document library: import drawer, loaded-row filter, ingestion inspector.
 * Mutations live in `useDocumentLibrary`. This file composes views.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { HandshakeBanner } from "../auth/auth-screens";
import { DocumentList } from "./document-list";
import { DocumentDeleteSheet } from "./document-delete-sheet";
import { IngestionStatus } from "./ingestion-status";
import { ImportSourceSheet } from "./import-source-sheet";
import { useDocumentLibrary } from "./hooks/use-document-library";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { PageHeader } from "../ui/page-header";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import styles from "./documents.module.css";

/**
 * Document library and upload/crawl convenience.
 *
 * @returns Library surface.
 * @remarks
 * File import is still reserve → Storage JWT → finalize. List status polls
 * while a loaded version is non-terminal and the tab is visible. Duplicate
 * upload clicks reuse one idempotency key until success.
 */
export function DocumentLibrary() {
  const router = useRouter();
  const lib = useDocumentLibrary();

  if (!lib.signedIn) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const importButton =
    lib.showUpload || lib.showCrawl ? (
      <Button
        type="button"
        variant="primary"
        data-action-id="documents.import"
        onClick={() => lib.setImportOpen(true)}
      >
        Import source
      </Button>
    ) : null;

  return (
    <div className={styles.page}>
      <PageHeader
        description="Upload files or add approved websites, then track search and graph readiness."
        actions={importButton}
      />
      <HandshakeBanner />

      <div className={styles.toolbar}>
        <div className={styles.toolbarFilter}>
          <Input
            label="Filter by name"
            leadingIcon="search"
            placeholder="Filter by name…"
            value={lib.filter}
            onChange={(event) => lib.onFilter(event.target.value)}
          />
          <p className={styles.toolbarSummary}>
            The filter only searches documents already loaded on this page.
          </p>
        </div>
        <p className={styles.toolbarCount}>
          Showing {String(lib.visibleDocs.length)} of {String(lib.loaded.length)}{" "}
          loaded
        </p>
      </div>

      {lib.documentsPending ? (
        <p className={styles.muted}>Loading documents</p>
      ) : (
        <>
          {lib.showDeleted ? (
            <StatusBanner kind="success" role="status">
              Document deleted.
            </StatusBanner>
          ) : null}
          <DocumentList
            documents={lib.visibleDocs}
            statusByVersionId={lib.statusByVersionId}
            pendingStatusIds={lib.pendingStatusIds}
            onLoadStatus={lib.openInspector}
            onViewDetails={(documentId) => {
              router.push(`/documents/${documentId}`);
            }}
            canDelete={lib.canDelete}
            onDelete={lib.openDelete}
            emptyAction={lib.loaded.length === 0 ? importButton : null}
            emptyTitle={
              lib.loaded.length === 0
                ? "No documents yet."
                : "No matching loaded documents."
            }
            emptyBody={
              lib.loaded.length === 0
                ? "Import a file or approved website to create searchable company knowledge."
                : "Filters apply only to documents already loaded."
            }
          />
          {lib.nextCursor !== null ? (
            <div className={styles.loadMore}>
              <Button
                type="button"
                variant="secondary"
                pending={lib.loadMorePending}
                pendingLabel="Loading…"
                onClick={lib.loadMore}
              >
                Load more
              </Button>
            </div>
          ) : null}
        </>
      )}

      {lib.importOpen && (lib.showUpload || lib.showCrawl) ? (
        <ImportSourceSheet
          onClose={() => lib.setImportOpen(false)}
          tab={lib.importTab}
          onTabChange={lib.setImportTab}
          showUpload={lib.showUpload}
          showCrawl={lib.showCrawl}
          file={lib.file}
          onFile={lib.setFile}
          category={lib.category}
          onCategory={lib.setCategory}
          title={lib.title}
          onTitle={lib.setTitle}
          attested={lib.attested}
          onAttested={lib.setAttested}
          allowPaidPost={lib.allowPaidPost}
          onUpload={lib.upload}
          uploadPhase={lib.uploadPhase}
          uploadNote={lib.uploadNote}
          uploadError={lib.uploadError}
          uploadPending={lib.uploadPending}
          startUrl={lib.startUrl}
          onStartUrl={lib.setStartUrl}
          approvedDomain={lib.approvedDomain}
          onApprovedDomain={lib.setApprovedDomain}
          crawlTitle={lib.crawlTitle}
          onCrawlTitle={lib.setCrawlTitle}
          maxDepth={lib.maxDepth}
          onMaxDepth={lib.setMaxDepth}
          maxPages={lib.maxPages}
          onMaxPages={lib.setMaxPages}
          onCrawl={lib.crawl}
          crawlError={lib.crawlError}
          crawlNote={lib.crawlNote}
          crawlPending={lib.crawlPending}
        />
      ) : null}

      {lib.inspectorOpen && lib.inspectorPayload ? (
        <IngestionStatus
          payload={lib.inspectorPayload}
          layout="timeline"
          asSheet
          onClose={lib.closeInspector}
          onRetry={lib.retryJob}
          retryPending={lib.retryPending}
        />
      ) : null}
      {lib.inspectorOpen && !lib.inspectorPayload ? (
        <Sheet title="Processing" onClose={lib.closeInspector}>
          <p className={styles.muted}>
            {lib.inspectorPending
              ? "Loading…"
              : "Processing details could not be loaded."}
          </p>
        </Sheet>
      ) : null}
      {lib.deleteTarget !== null ? (
        <DocumentDeleteSheet
          label={lib.deleteTarget.title ?? lib.deleteTarget.document_id}
          deleteError={lib.deleteError}
          pending={lib.deletePending}
          onClose={lib.closeDelete}
          onConfirm={lib.confirmDelete}
        />
      ) : null}
    </div>
  );
}
