/**
 * Reserve → upload → finalize and website crawl mutations.
 */

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  enqueueWebsiteCrawl,
  finalizeUpload,
  reserveUpload,
  type ApiAuth,
} from "../../../lib/api";
import { useSession } from "../../../lib/auth/session-provider";
import {
  ATTESTATION_POLICY_VERSION,
  CRAWL_CONTENT_CLASS_DEFAULT,
  CRAWL_MAX_DEPTH_DEFAULT,
  CRAWL_MAX_PAGES_DEFAULT,
  type DeclaredCategory,
} from "../../../lib/attestation";
import type { HandshakeDecision } from "../../../lib/handshake";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { sessionQueryKeys } from "../../../lib/query-keys";
import {
  objectNameForUpload,
  sha256Hex,
  uploadReservedObject,
} from "../../../lib/upload-client";
import type { ImportSourceTab } from "../import-source-sheet";

/**
 * Own import drawer state and paid upload/crawl mutations.
 *
 * Duplicate upload clicks reuse one idempotency key until success. Crawl
 * rotates its key only after a successful enqueue.
 *
 * @param auth - Bearer wrapper, or null when signed out.
 * @param handshake - Paid POST gate. Client checks are convenience only.
 * @returns Controlled import fields and mutation handles.
 */
export function useDocumentLibraryImport(
  auth: ApiAuth | null,
  handshake: HandshakeDecision,
) {
  const queryClient = useQueryClient();
  const session = useSession();
  const keys = sessionQueryKeys(session.accessToken);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DeclaredCategory>("allowed");
  const [title, setTitle] = useState("");
  const [attested, setAttested] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<string | null>(null);
  const [startUrl, setStartUrl] = useState("");
  const [approvedDomain, setApprovedDomain] = useState("");
  const [crawlTitle, setCrawlTitle] = useState("");
  const [maxDepth, setMaxDepth] = useState(CRAWL_MAX_DEPTH_DEFAULT);
  const [maxPages, setMaxPages] = useState(CRAWL_MAX_PAGES_DEFAULT);
  const [crawlNote, setCrawlNote] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<ImportSourceTab>("file");
  const uploadKeyRef = useRef(newIdempotencyKey());
  const crawlKeyRef = useRef(newIdempotencyKey());

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || file === null) {
        throw new Error("upload_missing_file");
      }
      if (!handshake.allowPaidPost) {
        throw new Error("handshake_blocked");
      }
      const idempotencyKey = uploadKeyRef.current;
      setUploadPhase("Reserving");
      const reserved = await reserveUpload(auth, file.size, idempotencyKey);
      const objectName = objectNameForUpload(reserved.storage_path, file.name);
      const hash = await sha256Hex(file);
      const supabase = session.supabase;
      if (supabase !== null && reserved.signed_url === null) {
        setUploadPhase("Uploading");
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
      setUploadPhase("Finalizing");
      return finalizeUpload(auth, {
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
    },
    onSuccess: (finalized) => {
      uploadKeyRef.current = newIdempotencyKey();
      setUploadPhase("Queued");
      setUploadNote(
        `Created document ${finalized.document_id}, version ${finalized.version_id}, job ${finalized.job_id}. The file is in quarantine until ingestion finishes.`,
      );
      void queryClient.invalidateQueries({ queryKey: keys.documents });
    },
    onError: () => {
      setUploadPhase("Failed");
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
        idempotency_key: crawlKeyRef.current,
        document_title: crawlTitle.trim() === "" ? null : crawlTitle,
        max_depth: maxDepth,
        max_pages: maxPages,
        content_class: CRAWL_CONTENT_CLASS_DEFAULT,
        graph_eligible: false,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
      });
    },
    onSuccess: (result) => {
      crawlKeyRef.current = newIdempotencyKey();
      setCrawlNote(`Created document ${result.document_id}, job ${result.job_id}.`);
      void queryClient.invalidateQueries({ queryKey: keys.documents });
    },
  });

  return {
    importOpen,
    importTab,
    setImportOpen,
    setImportTab,
    file,
    setFile,
    category,
    setCategory,
    title,
    setTitle,
    attested,
    setAttested,
    upload: () => uploadMutation.mutate(),
    uploadPhase,
    uploadNote,
    uploadError: uploadMutation.error instanceof Error ? uploadMutation.error : null,
    uploadPending: uploadMutation.isPending,
    startUrl,
    setStartUrl,
    approvedDomain,
    setApprovedDomain,
    crawlTitle,
    setCrawlTitle,
    maxDepth,
    setMaxDepth,
    maxPages,
    setMaxPages,
    crawl: () => crawlMutation.mutate(),
    crawlError: crawlMutation.error instanceof Error ? crawlMutation.error : null,
    crawlNote,
    crawlPending: crawlMutation.isPending,
  };
}

/** Import controller returned by `useDocumentLibraryImport`. */
export type UseDocumentLibraryImportResult = ReturnType<typeof useDocumentLibraryImport>;
