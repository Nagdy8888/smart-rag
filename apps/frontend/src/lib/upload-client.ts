/**
 * Quarantine upload helpers: SHA-256, object keys, Storage JWT upload.
 *
 * Local `signed_url` is null. `upload_method` is `supabase_storage_jwt`.
 * Reserve alone is never Hybrid Ready.
 */

import type { createBrowserSupabase } from "./auth/browser";

/** Local upload method advertised by FastAPI. */
export const UPLOAD_METHOD_STORAGE_JWT = "supabase_storage_jwt";

/**
 * Hex-encode a SHA-256 digest of file bytes using Web Crypto.
 *
 * @param data - File or ArrayBuffer.
 * @returns 64-character lowercase hex. Matches `content_hash` length bounds.
 */
export async function sha256Hex(data: ArrayBuffer | Blob): Promise<string> {
  const buffer = data instanceof Blob ? await data.arrayBuffer() : data;
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Join reservation prefix `{user_id}/{reservation_id}/` with a basename.
 *
 * `storage_path` from reserve is a prefix. Finalize `object_name` is the
 * exact object key.
 *
 * @param storagePath - Reservation prefix.
 * @param filename - Hostile original filename; only the basename is kept.
 * @returns Object key without `..` segments.
 */
export function objectNameForUpload(
  storagePath: string,
  filename: string,
): string {
  const prefix = storagePath.endsWith("/") ? storagePath : `${storagePath}/`;
  const base =
    filename.replaceAll("\\", "/").split("/").pop()?.trim() || "upload.bin";
  const safe = base.replace(/[^\w.\-()+ ]+/g, "_").slice(0, 200) || "upload.bin";
  return `${prefix}${safe}`.replaceAll("..", "_");
}

export type StorageUploadResult = {
  ok: boolean;
  error: string | null;
};

/**
 * Upload bytes to the reserved quarantine object with the user JWT.
 *
 * Does not use service-role keys. Failure is returned honestly; callers must
 * not mark Hybrid Ready.
 *
 * @param supabase - Browser client from `@supabase/ssr`.
 * @param bucket - `storage_bucket` from reserve.
 * @param objectName - Exact object key.
 * @param file - Selected file.
 * @returns `{ ok, error }`.
 */
export async function uploadReservedObject(
  supabase: NonNullable<ReturnType<typeof createBrowserSupabase>>,
  bucket: string,
  objectName: string,
  file: File,
): Promise<StorageUploadResult> {
  const { error } = await supabase.storage.from(bucket).upload(objectName, file, {
    contentType: file.type || "application/octet-stream",
    upsert: false,
  });
  if (error) {
    return { ok: false, error: error.message };
  }
  return { ok: true, error: null };
}
