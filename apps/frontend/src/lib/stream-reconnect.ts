/**
 * Bounded SSE resume policy for Ask. Resume is always GET on the same run.
 */

/** Delay before each automatic resume attempt, in milliseconds. */
export const RECONNECT_DELAYS_MS = [500, 1500, 3000] as const;

/** Maximum automatic resume attempts after a disconnect. */
export const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS_MS.length;

/** Why automatic resume stopped. */
export type ReconnectStopReason =
  | "cancelled"
  | "terminal"
  | "signed_out"
  | "run_deleted"
  | "unmounted"
  | "exhausted";

/**
 * Return the delay before an automatic resume attempt.
 *
 * @param attemptIndex - Zero-based attempt index.
 * @returns Milliseconds to wait.
 * @throws If `attemptIndex` is outside `0..2`.
 */
export function reconnectDelayMs(attemptIndex: number): number {
  const delay = RECONNECT_DELAYS_MS[attemptIndex];
  if (delay === undefined) {
    throw new RangeError("reconnect attempt index is out of range");
  }
  return delay;
}

/**
 * Return whether automatic resume must stop before the next GET.
 *
 * @param input - Live abort and attempt counters.
 * @returns Stop reason, or null when the next GET may run.
 */
export function shouldStopReconnect(input: {
  attemptIndex: number;
  cancelled: boolean;
  terminal: string | null;
  signedOut: boolean;
  runDeleted: boolean;
  unmounted: boolean;
  unauthorized?: boolean;
}): ReconnectStopReason | null {
  if (input.unmounted) {
    return "unmounted";
  }
  if (input.cancelled) {
    return "cancelled";
  }
  if (input.signedOut) {
    return "signed_out";
  }
  if (input.unauthorized === true) {
    return "signed_out";
  }
  if (input.runDeleted) {
    return "run_deleted";
  }
  if (input.terminal !== null) {
    return "terminal";
  }
  if (input.attemptIndex >= MAX_RECONNECT_ATTEMPTS) {
    return "exhausted";
  }
  return null;
}

/**
 * Wait `ms` unless the abort signal fires.
 *
 * @param ms - Delay in milliseconds.
 * @param signal - Abort signal from Cancel, unmount, or a new send.
 * @returns Resolves on timeout; rejects on abort.
 */
export async function waitForReconnectDelay(
  ms: number,
  signal: AbortSignal,
): Promise<void> {
  if (signal.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort(): void {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
