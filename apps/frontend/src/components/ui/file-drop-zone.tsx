/**
 * File drop zone. Does not upload, reserve, or call FastAPI.
 */

"use client";

import { useCallback, useId, useState, type DragEvent, type KeyboardEvent } from "react";
import { UserText } from "./user-text";
import styles from "./styles/controls.module.css";

export type FileDropZoneProps = {
  /** English instructions. */
  label?: string;
  /** Optional accept list forwarded to the hidden file input. */
  accept?: string;
  /** Called with the dropped or picked `File` list. Caller owns upload. */
  onFiles: (files: File[]) => void;
  /** Disabled visual state. Not an authorization decision. */
  disabled?: boolean;
};

/**
 * Render an accessible file picker plus drag target.
 *
 * @param props - Label, accept, and `onFiles`.
 * @returns Label wrapping a visually hidden file input.
 * @remarks
 * Side effects: invokes `onFiles` only. Does not POST. Filenames must be
 * rendered by the parent through `displayText`.
 */
export function FileDropZone({
  label = "Drop a file or choose one",
  accept,
  onFiles,
  disabled = false,
}: FileDropZoneProps) {
  const inputId = useId();
  const [active, setActive] = useState(false);

  const emit = useCallback(
    (list: FileList | null) => {
      if (disabled || list === null || list.length === 0) {
        return;
      }
      onFiles(Array.from(list));
    },
    [disabled, onFiles],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (!disabled) {
      setActive(true);
    }
  }, [disabled]);

  const onDragLeave = useCallback(() => {
    setActive(false);
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      setActive(false);
      emit(event.dataTransfer.files);
    },
    [emit],
  );

  const onKeyDown = useCallback((event: KeyboardEvent<HTMLLabelElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      document.getElementById(inputId)?.click();
    }
  }, [inputId]);

  const className = [styles.dropZone, active ? styles.dropZoneActive : undefined]
    .filter(Boolean)
    .join(" ");

  return (
    <label
      className={className}
      htmlFor={inputId}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onKeyDown={onKeyDown}
    >
      <UserText value={label} />
      <input
        id={inputId}
        className={styles.fileInput}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => emit(event.target.files)}
      />
    </label>
  );
}
