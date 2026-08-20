/**
 * Document library: cards, quota-aware upload, crawl (owner/admin convenience),
 * status pills from real version status.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { Button } from "./ui/button";
import { FileDropZone } from "./ui/file-drop-zone";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { RovingList } from "./ui/roving-list";
import { StatusBanner } from "./ui/status-banner";
import { StatusPill } from "./ui/status-pill";
import { UserText } from "./ui/user-text";
import {
  enqueueWebsiteCrawl,
  fetchMe,
  fetchMeta,
  fetchVersionStatus,
  finalizeUpload,
  listDocuments,
  reserveUpload,
  retryIngestionJob,
  type ApiAuth,
} from "../lib/api";
import { MFA_UPLOAD_DENIED } from "../lib/auth/copy";
import { useSession } from "../lib/auth/session-provider";
import {
  ATTESTATION_POLICY_VERSION,
  CRAWL_CONTENT_CLASS_DEFAULT,
  CRAWL_MAX_DEPTH_DEFAULT,
  CRAWL_MAX_PAGES_DEFAULT,
  DECLARED_CATEGORIES,
  type DeclaredCategory,
} from "../lib/attestation";
import { DOCUMENT_DELETE_UNAVAILABLE } from "../lib/citation-drawer";
import { evaluatePaidHandshake } from "../lib/handshake";
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
  ingestionStatusLabel,
  ingestionStatusTone,
} from "../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../lib/limitations";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { showCrawlConvenience, showUploadConvenience } from "../lib/roles";
import {
  objectNameForUpload,
  sha256Hex,
  uploadReservedObject,
} from "../lib/upload-client";
import styles from "./developer-app.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Document library and upload/crawl convenience.
 *
 * @returns Library surface.
 */
export function DocumentLibrary() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DeclaredCategory>("allowed");
  const [title, setTitle] = useState("");
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [startUrl, setStartUrl] = useState("");
  const [approvedDomain, setApprovedDomain] = useState("");
  const [statusVersionId, setStatusVersionId] = useState<string | null>(null);

  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
  });
  const handshake = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const documentsQuery = useQuery({
    queryKey: keys.documents,
    queryFn: () => listDocuments(auth as ApiAuth),
    enabled: auth !== null,
  });

  const versionQuery = useQuery({
    queryKey: keys.versionStatus(statusVersionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, statusVersionId as string),
    enabled: auth !== null && statusVersionId !== null,
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || file === null) {
        throw new Error("upload_missing_file");
      }
      if (!handshake.allowPaidPost) {
        throw new Error("handshake_blocked");
      }
      const idempotencyKey = newIdempotencyKey();
      const reserved = await reserveUpload(auth, file.size, idempotencyKey);
      const objectName = objectNameForUpload(reserved.storage_path, file.name);
      const hash = await sha256Hex(file);
      const supabase = session.supabase;
      if (supabase !== null && reserved.signed_url === null) {
        const uploaded = await uploadReservedObject(
          supabase,
          reserved.storage_bucket,
          objectName,
          file,
        );
        if (!uploaded.ok) {
          throw new Error(`storage_upload_failed:${uploaded.error ?? "unknown"}`);
        }
      }
      const finalized = await finalizeUpload(auth, {
        reservation_id: reserved.reservation_id,
        object_name: objectName,
        content_hash: hash,
        actual_bytes: file.size,
        media_type: file.type || null,
        declared_category: category,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
        idempotency_key: idempotencyKey,
        document_title: title || file.name,
      });
      return { reserved, finalized };
    },
    onSuccess: (result) => {
      setUploadNote(
        `Uploaded “${result.finalized.document_id}”. The file is in quarantine until ingestion finishes.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const crawlMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      return enqueueWebsiteCrawl(auth, {
        start_url: startUrl,
        approved_domain: approvedDomain,
        idempotency_key: newIdempotencyKey(),
        max_depth: CRAWL_MAX_DEPTH_DEFAULT,
        max_pages: CRAWL_MAX_PAGES_DEFAULT,
        content_class: CRAWL_CONTENT_CLASS_DEFAULT,
        graph_eligible: false,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: async (jobId: string) => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      return retryIngestionJob(auth, jobId);
    },
    onSuccess: () => {
      if (statusVersionId) {
        void queryClient.invalidateQueries({
          queryKey: keys.versionStatus(statusVersionId),
        });
      }
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.shell}>
        <h1>Documents</h1>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const role = meQuery.data?.role;
  const showUpload = showUploadConvenience(role, meQuery.data?.upload_enabled);
  const showCrawl = showCrawlConvenience(role);
  const version = versionQuery.data?.version ?? null;

  return (
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div>
          <h1>Document library</h1>
          <p className={styles.pageLead}>
            Manage authorized sources and follow ingestion status.
          </p>
        </div>
      </header>
      <HandshakeBanner />

      {showUpload ? (
        <section className={styles.panel} aria-label="Upload">
          <h2>Upload file</h2>
          <FileDropZone
            onFiles={(files) => setFile(files[0] ?? null)}
            disabled={!handshake.allowPaidPost}
          />
          {file ? (
            <p className={styles.muted}>
              <UserText value={file.name} /> — {String(file.size)} bytes
            </p>
          ) : null}
          <label>
            Declared category
            <select
              value={category}
              onChange={(event) =>
                setCategory(event.target.value as DeclaredCategory)
              }
            >
              {DECLARED_CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <p className={styles.muted}>
            Category and attestation are recorded with the upload. Files are not
            searchable until ingestion completes.
          </p>
          <Input
            label="Document title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <p className={styles.muted}>
            Uploads use your signed-in session. A reservation is never treated as
            ready for search.
          </p>
          <Button
            type="button"
            variant="primary"
            disabled={file === null || !handshake.allowPaidPost}
            onClick={() => uploadMutation.mutate()}
          >
            Reserve, upload, finalize
          </Button>
          {uploadNote ? <p className={styles.muted}>{uploadNote}</p> : null}
          {uploadMutation.isError ? (
            <StatusBanner kind="error" role="alert">
              {uploadMutation.error instanceof Error &&
              uploadMutation.error.message === "mfa_required"
                ? MFA_UPLOAD_DENIED
                : uploadMutation.error instanceof Error &&
                    uploadMutation.error.message.startsWith("storage_upload_failed")
                  ? "The file did not finish uploading. Try again after the storage write succeeds."
                  : "Upload rejected. Server authorization is authoritative."}
            </StatusBanner>
          ) : null}
        </section>
      ) : (
        <p className={styles.muted}>
          Upload controls are hidden as convenience only. The server still
          denies viewers and callers without upload_enabled.
        </p>
      )}

      {showCrawl ? (
        <section className={styles.panel} aria-label="Website crawl">
          <h2>Request website</h2>
          <Input
            label="Start URL"
            value={startUrl}
            onChange={(event) => setStartUrl(event.target.value)}
          />
          <Input
            label="Approved domain"
            value={approvedDomain}
            onChange={(event) => setApprovedDomain(event.target.value)}
          />
          <Button
            type="button"
            disabled={!handshake.allowPaidPost || startUrl.trim() === ""}
            onClick={() => crawlMutation.mutate()}
          >
            Enqueue crawl
          </Button>
          {crawlMutation.isError ? (
            <StatusBanner kind="error" role="alert">
              Crawl rejected. Members receive HTTP 403 from the server.
            </StatusBanner>
          ) : null}
        </section>
      ) : (
        <p className={styles.muted}>
          Website crawl is hidden for this role. The server still denies members
          and viewers.
        </p>
      )}

      <section className={styles.panel} aria-label="Library">
        <h2>Library</h2>
        {(documentsQuery.data ?? []).length === 0 ? (
          <EmptyState title="No documents you can see">
            Upload a file or wait for an invitation that grants access.
          </EmptyState>
        ) : null}
        <RovingList
          aria-label="Documents"
          className={styles.list}
          items={(documentsQuery.data ?? []).map((doc) => ({
            id: doc.document_id,
            item: doc,
          }))}
          onSelect={(doc) => {
            void router.push(`/documents/${doc.document_id}`);
          }}
        >
          {(doc) => (
            <>
              <UserText value={doc.title ?? doc.document_id} />
              {" — "}
              <StatusPill status={doc.visibility} />
            </>
          )}
        </RovingList>
        <ul className={styles.list} aria-label="Version status shortcuts">
          {(documentsQuery.data ?? []).map((doc) => (
            <li key={`status-${doc.document_id}`}>
              <span className={styles.muted}>
                Version{" "}
                <UserText value={doc.current_version_id ?? "none"} />
              </span>
              {doc.current_version_id ? (
                <Button
                  type="button"
                  onClick={() => setStatusVersionId(doc.current_version_id)}
                >
                  Load status
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      {version ? (
        <section className={styles.panel} aria-label="Version status">
          <h2>Ingestion status</h2>
          <StatusPill
            status={ingestionStatusLabel(version.status)}
            tone={ingestionStatusTone(version.status)}
          />
          <dl>
            <dt>BM25</dt>
            <dd>{formatBm25Summary(version.bm25)}</dd>
            <dt>Graph handoff</dt>
            <dd>{formatGraphHandoffSummary(version.graph_handoff)}</dd>
            <dt>Scan</dt>
            <dd>
              <UserText value={version.scan?.result ?? "none"} />
            </dd>
            <dt>Attestation</dt>
            <dd>
              <UserText value={version.review?.declared_category ?? "none"} />{" "}
              <UserText
                value={version.review?.attestation_policy_version ?? ""}
              />
            </dd>
          </dl>
          {version.status === "graph_pending" ||
          !version.document_graph_eligible ? (
            <LimitationCallout tone="warning">
              {limitationCopy("graph_pending")} {graphNotReadyCopy(1)}
            </LimitationCallout>
          ) : null}
          {version.status === "deletion_pending" ? (
            <StatusPill status="deletion_pending" tone="warning" />
          ) : null}
          <p className={styles.muted}>{DOCUMENT_DELETE_UNAVAILABLE}</p>
          <ul className={styles.list}>
            {(versionQuery.data?.recent_jobs ?? []).map((job) => (
              <li key={job.id}>
                <UserText value={job.job_kind} /> —{" "}
                <UserText value={job.status} />
                {version.retry_allowed ? (
                  <Button
                    type="button"
                    onClick={() => retryMutation.mutate(job.id)}
                  >
                    Retry
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
