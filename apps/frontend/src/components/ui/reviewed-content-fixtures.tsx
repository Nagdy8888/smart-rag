/**
 * Reviewed Arabic/mixed-direction, XSS, and logical-highlight fixtures.
 *
 * Missing Stitch RTL/mobile frames are not a waiver: this panel is the
 * reviewed gap fill. Strings are React text nodes only.
 */

"use client";

import {
  BIDI_CONTROL,
  CITATION_LOGICAL_SENTENCE,
  DIACRITICS_AR,
  LONG_URL,
  MIXED_BIDI,
  MIXED_POLICY_CODE,
  MIXED_POLICY_CODE_ISOLATE,
  XSS_ENTITY,
  XSS_FILENAME,
  XSS_JAVASCRIPT_URL,
} from "../../lib/hostile-text-fixtures";
import {
  CITATION_LOGICAL_END,
  CITATION_LOGICAL_START,
} from "../../lib/highlight-logical-range";
import { CitationChip } from "./citation-chip";
import { LogicalHighlight } from "./logical-highlight";
import { StatusBanner } from "./status-banner";
import { Textarea } from "./textarea";
import { CodeText, UserText } from "./user-text";
import styles from "./ui.module.css";

/**
 * Render the brief's mixed-direction and XSS fixtures as inert text.
 *
 * @returns Region with composer-like textarea, banners, and citation chips.
 * @remarks
 * Not live diagnostics. Not an Auth bypass. Used so zoom/keyboard tests
 * can see composer, banners, and chips without a session.
 */
export function ReviewedContentFixtures() {
  return (
    <section
      className={styles.fixturePanel}
      aria-label="Reviewed mixed-direction fixtures"
      data-testid="reviewed-content-fixtures"
    >
      <h2>Reviewed mixed-direction fixtures</h2>
      <p className={styles.fixtureNote}>
        The delivered design export had no RTL or mobile frames. These
        strings are the reviewed gap fill, not live retrieval.
      </p>
      <StatusBanner kind="info" role="status">
        Fixture banner for zoom and keyboard checks.
      </StatusBanner>
      <Textarea
        id="stub-composer"
        label="Stub composer"
        readOnly
        rows={3}
        value={MIXED_BIDI}
      />
      <p>
        Mixed: <UserText value={MIXED_BIDI} />
      </p>
      <p>
        Policy: <UserText value={MIXED_POLICY_CODE} /> isolated{" "}
        <CodeText value={MIXED_POLICY_CODE_ISOLATE} />
      </p>
      <p className={styles.diacriticLine}>
        Diacritics: <UserText value={DIACRITICS_AR} />
      </p>
      <p>
        Long URL: <CodeText value={LONG_URL} className={styles.longUrl} />
      </p>
      <p>
        Filename: <UserText value={XSS_FILENAME} />
      </p>
      <p>
        Entity: <UserText value={XSS_ENTITY} />
      </p>
      <p>
        javascript URL: <CodeText value={XSS_JAVASCRIPT_URL} />
      </p>
      <p>
        Bidi control: <UserText value={BIDI_CONTROL} />
      </p>
      <p>
        Logical highlight:{" "}
        <LogicalHighlight
          text={CITATION_LOGICAL_SENTENCE}
          start={CITATION_LOGICAL_START}
          end={CITATION_LOGICAL_END}
        />
      </p>
      <CitationChip index={1} citationId={XSS_FILENAME} />
    </section>
  );
}
