/**
 * Loading indicator. Animation is disabled under `prefers-reduced-motion`.
 */

import styles from "./styles/data-display.module.css";

export type SpinnerProps = {
  /** Accessible name. Default `Loading`. */
  label?: string;
};

/**
 * Render a busy status with `aria-busy`.
 *
 * @param props - Optional label.
 * @returns Status element. No timeout or fetch.
 */
export function Spinner({ label = "Loading" }: SpinnerProps) {
  return (
    <span className={styles.spinner} role="status" aria-busy="true" aria-label={label} />
  );
}
