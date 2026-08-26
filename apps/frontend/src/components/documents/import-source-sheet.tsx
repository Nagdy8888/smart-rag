/**
 * Import source sheet: Files and Website tabs gated by role convenience helpers.
 */

import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { ImportFileTab, type ImportFileTabProps } from "./import-file-tab";
import { ImportWebsiteTab, type ImportWebsiteTabProps } from "./import-website-tab";
import styles from "./documents.module.css";

export type ImportSourceTab = "file" | "website";

export type ImportSourceSheetProps = ImportFileTabProps &
  ImportWebsiteTabProps & {
    /** Close handler. */
    onClose: () => void;
    /** Active tab. */
    tab: ImportSourceTab;
    /** Tab change. */
    onTabChange: (tab: ImportSourceTab) => void;
    /** File tab convenience. */
    showUpload: boolean;
    /** Website tab convenience. */
    showCrawl: boolean;
  };

/**
 * Render the import drawer. Tabs are omitted when the matching convenience
 * helper is false; hidden chrome is not authorization.
 *
 * @param props - Controlled import fields and existing mutations.
 * @returns Modal sheet. Does not call FastAPI.
 */
export function ImportSourceSheet({
  onClose,
  tab,
  onTabChange,
  showUpload,
  showCrawl,
  ...tabProps
}: ImportSourceSheetProps) {
  const showFileTab = showUpload;
  const showWebsiteTab = showCrawl;
  const active: ImportSourceTab =
    tab === "website" && showWebsiteTab
      ? "website"
      : showFileTab
        ? "file"
        : "website";
  return (
    <Sheet title="Import source" onClose={onClose}>
      <div className={styles.tabs}>
        {showFileTab ? (
          <Button
            type="button"
            variant={active === "file" ? "primary" : "secondary"}
            onClick={() => onTabChange("file")}
          >
            Files
          </Button>
        ) : null}
        {showWebsiteTab ? (
          <Button
            type="button"
            variant={active === "website" ? "primary" : "secondary"}
            onClick={() => onTabChange("website")}
          >
            Website
          </Button>
        ) : null}
      </div>
      {active === "file" && showFileTab ? <ImportFileTab {...tabProps} /> : null}
      {active === "website" && showWebsiteTab ? (
        <ImportWebsiteTab {...tabProps} />
      ) : null}
    </Sheet>
  );
}
