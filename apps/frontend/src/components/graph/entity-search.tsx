/**
 * Entity search: submit only for queries meeting GET /graph/entities/search.
 */

"use client";

import type { FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  graphSearchQueryIsRunnable,
} from "../../lib/graph-client";
import type { GraphEntityResponse } from "../../lib/types";
import styles from "./graph.module.css";

export type EntitySearchProps = {
  /** Draft query. */
  query: string;
  /** Draft change. */
  onQuery: (value: string) => void;
  /** Submit search. */
  onSearch: () => void;
  /** Hits from GET search. */
  hits: GraphEntityResponse[];
  /** Select a hit as an inspect chip. Does not inspect by itself. */
  onSelect: (hit: GraphEntityResponse) => void;
  /** Loading flag. */
  loading: boolean;
  /** True after a submitted search returned no hits. */
  searched: boolean;
};

/**
 * Render entity search.
 *
 * @param props - Query, hits, and select callback.
 * @returns Search column. Selecting a hit adds a chip; it does not POST inspect.
 */
export function EntitySearch({
  query,
  onQuery,
  onSearch,
  hits,
  onSelect,
  loading,
  searched,
}: EntitySearchProps) {
  const runnable = graphSearchQueryIsRunnable(query);

  /**
   * Submit only when the trimmed query meets the API minimum.
   *
   * @param event - Form submit.
   */
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!runnable) {
      return;
    }
    onSearch();
  }

  return (
    <section className={styles.search} aria-label="Search entities">
      <form className={styles.searchForm} onSubmit={handleSubmit}>
        <Input
          label="Search entities."
          value={query}
          leadingIcon="search"
          onChange={(event) => onQuery(event.target.value)}
        />
        <Button type="submit" disabled={!runnable} disabledReason={runnable ? undefined : "Enter a search query."}>
          Search
        </Button>
      </form>
      {loading ? <p className={styles.muted}>Searching</p> : null}
      {searched && !loading && hits.length === 0 ? (
        <p className={styles.muted}>No authorized entities for this query.</p>
      ) : null}
      <ul className={styles.hitList}>
        {hits.map((hit) => (
          <li key={`${hit.object_id}-${hit.chunk_id}`}>
            <button type="button" className={styles.hitButton} onClick={() => onSelect(hit)}>
              <StatusPill status={hit.object_type} />
              <span className={styles.mono}>
                <UserText value={hit.object_id} />
              </span>
              <span className={styles.muted}>support {String(hit.support)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
