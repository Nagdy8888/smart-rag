"use client";

import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { listWorkspaceUsers } from "../../lib/api";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { sessionCacheScope } from "../../lib/query-keys";
import { displayText } from "../../lib/safe-text";
import { Select } from "./select";

/** Pick active teammates by name; assigning responsibility never grants access. */
export function KnowledgeOwnerSelect({ label, value, onChange, reviewersOnly = false }: {
  label: string; value: string; onChange: (value: string) => void; reviewersOnly?: boolean;
}) {
  const fieldId = useId();
  const auth = useApiAuth();
  const query = useQuery({ queryKey: ["knowledge-team", sessionCacheScope(auth?.accessToken ?? null)],
    queryFn: () => listWorkspaceUsers(auth!), enabled: auth !== null });
  const members = query.data?.members.filter((member) => !member.disabled_at &&
    (!reviewersOnly || member.role === "owner" || member.role === "admin")) ?? [];
  return <div><Select id={fieldId} fullWidth label={label} value={value} disabled={query.isPending || query.isError}
    options={[{ value: "", label: "Unassigned" },
      ...(value && !members.some((member) => member.user_id === value) ? [{ value, label: "Current assignee" }] : []),
      ...members.map((member) => ({ value: member.user_id, label: displayText(member.display_name ?? member.email) }))]}
    onChange={(event) => onChange(event.target.value)} />
    {query.isError ? <p role="alert">Teammates could not be loaded. <button onClick={() => void query.refetch()}>Retry</button></p> : null}
  </div>;
}
