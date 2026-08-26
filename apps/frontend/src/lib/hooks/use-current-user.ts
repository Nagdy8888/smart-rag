/**
 * Session-scoped `/me` query. Server `/me` remains the role authority.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMe, type ApiAuth } from "../api";
import { useApiAuth } from "../auth/use-api-auth";
import { useSession } from "../auth/session-provider";
import { sessionQueryKeys } from "../query-keys";
import type { CurrentUserResponse } from "../types";

export type UseCurrentUserResult = {
  currentUser: CurrentUserResponse | null;
  currentUserPending: boolean;
  currentUserError: unknown;
  isFetched: boolean;
};

/**
 * Load the current caller from FastAPI `/me`.
 *
 * @returns Explicit pending/error/data fields. Cache key is `["me", sub]`.
 */
export function useCurrentUser(): UseCurrentUserResult {
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const query = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null && session.ready,
  });
  return {
    currentUser: query.data ?? null,
    currentUserPending: query.isPending,
    currentUserError: query.error,
    isFetched: query.isFetched,
  };
}
