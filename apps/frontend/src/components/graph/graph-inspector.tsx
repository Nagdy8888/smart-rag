/**
 * Locators and limitations inspector.
 */

import { LimitationCallout } from "../ui/limitation-callout";
import { UserText } from "../ui/user-text";
import {
  graphLimitationDisplay,
  isGraphPendingLimitation,
} from "../../lib/graph-client";
import { graphNotReadyCopy, limitationCopy, limitationTone } from "../../lib/limitations";
import { formatProvenance } from "../../lib/safe-text";
import type {
  GraphInspectLimitation,
  GraphInspectLocator,
} from "../../lib/types";
import styles from "./graph.module.css";

export type GraphInspectorProps = {
  /** Canonical locators. */
  locators: GraphInspectLocator[];
  /** Server limitations. */
  limitations: GraphInspectLimitation[];
};

/**
 * Render locators and signed limitation copy.
 *
 * @param props - Locators and limitations.
 * @returns Inspector column. ACL blindness never interpolates count.
 */
export function GraphInspector({ locators, limitations }: GraphInspectorProps) {
  return (
    <section className={styles.inspector} aria-label="Locators and limitations">
      <h2>Locators</h2>
      <ul className={styles.list}>
        {locators.map((locator) => (
          <li key={locator.chunk_id}>
            <UserText
              value={formatProvenance({
                page_number: locator.page_number,
                section_path: locator.section_path,
                sheet_name: locator.sheet_name,
                range_ref: locator.range_ref,
                source_url: locator.source_url,
              })}
            />
          </li>
        ))}
      </ul>
      {limitations.map((item) => (
        <LimitationCallout key={item.code} tone={limitationTone(item.code)}>
          {graphLimitationDisplay(item)}
          {isGraphPendingLimitation(item.code) && item.code !== "graph_acl_blindness"
            ? ` ${graphNotReadyCopy(item.count ?? 0)}`
            : null}
        </LimitationCallout>
      ))}
      {limitations.some((item) => item.code === "graph_acl_blindness") ? (
        <p className={styles.muted}>{limitationCopy("graph_acl_blindness")}</p>
      ) : null}
      <p className={styles.muted}>
        Relationship editing is not available. This explorer is inspection-only.
      </p>
    </section>
  );
}
