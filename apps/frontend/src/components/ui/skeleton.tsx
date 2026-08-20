/**
 * Loading placeholder. Pulse is disabled under `prefers-reduced-motion`.
 */

import styles from "./ui.module.css";

export type SkeletonProps = {
  /** Accessible busy label. Default `Loading`. */
  label?: string;
  /** Optional width, for example `12rem`. */
  width?: string;
};

/**
 * Render a busy skeleton bar.
 *
 * @param props - Label and optional width.
 * @returns `role="status"` placeholder. No timeout.
 */
export function Skeleton({ label = "Loading", width }: SkeletonProps) {
  return (
    <span
      className={styles.skeleton}
      role="status"
      aria-busy="true"
      aria-label={label}
      style={width ? { width } : undefined}
    />
  );
}
