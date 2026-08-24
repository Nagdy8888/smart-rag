/**
 * Bounded waits for Auth calls that otherwise freeze the console.
 */

/** Password sign-in against hosted Auth. */
export const SIGN_IN_TIMEOUT_MS = 12_000;

/** Browser `getSession` restore after navigation. */
export const SESSION_RESTORE_TIMEOUT_MS = 8_000;

/** Next.js proxy `getClaims` on each document request. */
export const AUTH_CLAIMS_TIMEOUT_MS = 5_000;

/**
 * Reject when `promise` does not settle in time.
 *
 * @param promise - Auth or network work.
 * @param timeoutMs - Limit in milliseconds.
 * @param label - Error message on expiry. Never a provider trace.
 * @returns The settled value.
 * @throws Error when the timer fires first, or the original rejection.
 */
export function raceTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  label: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(label));
    }, timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}
