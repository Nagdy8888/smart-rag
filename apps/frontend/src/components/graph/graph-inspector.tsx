/**
 * Evidence details: identity, hop/support, locators, and limitation codes.
 * Relationship editing is omitted; there is no graph mutation API.
 */

import { CodeText, UserText } from "../ui/user-text";
import { LimitationCallout } from "../ui/limitation-callout";
import {
  graphLimitationDisplay,
  isGraphOutageLimitation,
  isGraphPendingLimitation,
} from "../../lib/graph-client";
import { graphNotReadyCopy, limitationTone } from "../../lib/limitations";
import type {
  GraphInspectLimitation,
  GraphInspectLocator,
  GraphInspectNodeResponse,
} from "../../lib/types";
import styles from "./graph.module.css";

export type GraphInspectorProps = {
  /** Selected inspect node, if any. */
  node: GraphInspectNodeResponse | null;
  /** Canonical locators for the inspect payload. */
  locators: GraphInspectLocator[];
  /** Server limitations. */
  limitations: GraphInspectLimitation[];
};

/**
 * Render identity, locators, and signed limitation copy.
 *
 * @param props - Selected node, locators, and limitations.
 * @returns Inspector body. ACL blindness never interpolates count.
 */
export function GraphInspector({ node, locators, limitations }: GraphInspectorProps) {
  const related =
    node === null
      ? []
      : locators.filter(
          (locator) =>
            locator.chunk_id === node.chunk_id ||
            locator.document_id === node.document_id,
        );
  const shown = related.length > 0 ? related : locators;

  return (
    <div className={styles.inspectorBody}>
      <h2>Evidence details.</h2>
      {node ? (
        <dl className={styles.dl}>
          <dt>Type</dt>
          <dd>
            <UserText value={node.object_type} />
          </dd>
          <dt>Object ID</dt>
          <dd>
            <CodeText value={node.object_id} />
          </dd>
          <dt>Document ID</dt>
          <dd>
            <CodeText value={node.document_id} />
          </dd>
          <dt>Version ID</dt>
          <dd>
            <CodeText value={node.version_id} />
          </dd>
          <dt>Chunk ID</dt>
          <dd>
            <CodeText value={node.chunk_id} />
          </dd>
          <dt>Hop</dt>
          <dd>{String(node.hop)}</dd>
          <dt>Support</dt>
          <dd>{String(node.support)}</dd>
        </dl>
      ) : (
        <p className={styles.muted}>Select a node to inspect evidence.</p>
      )}
      {shown.map((locator) => (
        <article key={locator.chunk_id} className={styles.locatorCard}>
          <dl className={styles.dl}>
            <dt>page</dt>
            <dd>{locator.page_number === null ? "—" : String(locator.page_number)}</dd>
            <dt>section</dt>
            <dd>
              <UserText
                value={locator.section_path.length > 0 ? locator.section_path.join(" / ") : "—"}
              />
            </dd>
            <dt>sheet</dt>
            <dd>
              <UserText value={locator.sheet_name ?? "—"} />
            </dd>
            <dt>range</dt>
            <dd className={styles.mono}>
              <CodeText value={locator.range_ref ?? "—"} />
            </dd>
            <dt>url</dt>
            <dd>
              <CodeText value={locator.source_url ?? "—"} />
            </dd>
          </dl>
        </article>
      ))}
      {limitations.map((item) => (
        <LimitationCallout key={item.code} tone={limitationTone(item.code)}>
          {graphLimitationDisplay(item)}
          {isGraphPendingLimitation(item.code)
            ? ` ${graphNotReadyCopy(item.count ?? 0)}`
            : null}
          {isGraphOutageLimitation(item.code) ? " Graph-only is not an answering mode." : null}
        </LimitationCallout>
      ))}
    </div>
  );
}
