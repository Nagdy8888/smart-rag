/**
 * Admin Evaluation workspace: review, required sources, and official exams.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { fetchPdfEvalStatus, type ApiAuth } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import { ErrorState } from "../ui/error-state";
import { Spinner } from "../ui/spinner";
import { EvaluationWorkspace } from "./evaluation-workspace";
import styles from "./evaluation.module.css";

/**
 * Render the hosted PDF evaluation workspace.
 *
 * Capability is gated by `/api/meta`. Private content still requires a real
 * owner/admin GET. Hidden nav is not authorization.
 *
 * @returns Evaluation panel, or a permission/error state.
 */
export function EvaluationPanel() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const statusQuery = useQuery({
    queryKey: keys.pdfEvalStatus,
    queryFn: () => fetchPdfEvalStatus(auth as ApiAuth),
    enabled: auth !== null,
    retry: false,
  });

  if (!session.ready || accessToken === null || auth === null) {
    return <p className={styles.muted}>Sign in to review evaluation cases.</p>;
  }
  if (statusQuery.isPending) {
    return <Spinner label="Loading evaluation workspace" />;
  }
  if (statusQuery.error instanceof Error && statusQuery.error.message === "forbidden") {
    return (
      <ErrorState
        title="You don’t have access."
        message="This area is limited to owners and admins. The server denied the request."
      />
    );
  }
  if (statusQuery.error) {
    return (
      <ErrorState
        title="Evaluation is unavailable."
        message="The evaluation workspace could not be loaded."
      />
    );
  }

  return (
    <section className={styles.workspace} aria-label="Evaluation workspace">
      <h2>Evaluation</h2>
      <p className={styles.lead}>
        Build a trusted set of questions, verify the required sources, and
        measure how often document search finds them.
      </p>
      <EvaluationWorkspace auth={auth} status={statusQuery.data} />
    </section>
  );
}
