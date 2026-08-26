/**
 * Tab wrap inside a modal root and restore the opening trigger on cleanup.
 */

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type TrapFocusOptions = {
  /** Element that opened the surface. Restored on cleanup. */
  returnFocus?: HTMLElement | null;
  /** First focus target. Defaults to the first enabled control. */
  initialFocus?: HTMLElement | null;
};

/**
 * Return whether a keyboard event target is an editable control.
 *
 * @param target - Event target from a window keydown.
 * @returns True for input, textarea, select, or contenteditable.
 */
export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return (
    target.isContentEditable ||
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT"
  );
}

/**
 * List enabled focusable descendants in DOM order.
 *
 * @param root - Modal or menu root.
 * @returns Focusable elements that are not disabled.
 */
export function getFocusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (node) => !node.hasAttribute("disabled"),
  );
}

/**
 * Trap Tab/Shift+Tab inside `root` and restore `returnFocus` on cleanup.
 *
 * @param root - Element that should contain keyboard focus.
 * @param options - Optional restore target and initial focus.
 * @returns Cleanup that removes the listener and restores focus.
 * @remarks
 * Escape is left to the caller. Does not change body scroll. Unmount must
 * call the returned function exactly once.
 */
export function trapFocus(
  root: HTMLElement,
  options: TrapFocusOptions = {},
): () => void {
  const previouslyFocused =
    options.returnFocus ?? (document.activeElement as HTMLElement | null);
  const initial = options.initialFocus ?? getFocusableElements(root)[0];
  initial?.focus();

  /**
   * Wrap Tab at the first and last enabled control.
   *
   * @param event - Document or root keyboard event.
   */
  function onKeyDown(event: KeyboardEvent): void {
    if (event.key !== "Tab") {
      return;
    }
    const nodes = getFocusableElements(root);
    if (nodes.length === 0) {
      event.preventDefault();
      return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (first === undefined || last === undefined) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  root.addEventListener("keydown", onKeyDown);
  return () => {
    root.removeEventListener("keydown", onKeyDown);
    previouslyFocused?.focus();
  };
}
