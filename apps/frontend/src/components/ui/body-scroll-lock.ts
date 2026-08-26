/**
 * Nested document-body scroll lock. The first acquire hides overflow; the
 * last matching release restores the overflow that was present then.
 */

let lockCount = 0;
let previousOverflow = "";

/**
 * Lock `document.body` overflow. Safe to call while another lock is held.
 *
 * @returns Release that restores overflow only after the last lock ends.
 *   Calling release twice is a no-op. Side effect: writes `body.style.overflow`.
 */
export function lockBodyScroll(): () => void {
  if (typeof document === "undefined") {
    return () => undefined;
  }
  if (lockCount === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  lockCount += 1;
  let released = false;
  return () => {
    if (released || typeof document === "undefined") {
      return;
    }
    released = true;
    lockCount = Math.max(0, lockCount - 1);
    if (lockCount === 0) {
      document.body.style.overflow = previousOverflow;
    }
  };
}
