/**
 * Entity search column.
 */

import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { UserText } from "../ui/user-text";
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
  /** Select a hit. */
  onSelect: (objectId: string) => void;
  /** Loading flag. */
  loading: boolean;
};

/**
 * Render entity search.
 *
 * @param props - Query, hits, and select callback.
 * @returns Search column. Selecting a hit inspects that object_id.
 */
export function EntitySearch({
  query,
  onQuery,
  onSearch,
  hits,
  onSelect,
  loading,
}: EntitySearchProps) {
  return (
    <section className={styles.search} aria-label="Search">
      <h2>Search</h2>
      <Input
        label="Entity query"
        value={query}
        onChange={(event) => onQuery(event.target.value)}
      />
      <Button type="button" onClick={onSearch} disabled={query.trim() === ""}>
        Search
      </Button>
      {loading ? <p className={styles.muted}>Searching</p> : null}
      {!loading && hits.length === 0 ? (
        <p className={styles.muted}>No authorized entities for this query.</p>
      ) : null}
      <ul className={styles.list}>
        {hits.map((hit) => (
          <li key={`${hit.object_id}-${hit.chunk_id}`}>
            <button type="button" onClick={() => onSelect(hit.object_id)}>
              <UserText value={hit.object_type} />{" "}
              <UserText value={hit.object_id} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
