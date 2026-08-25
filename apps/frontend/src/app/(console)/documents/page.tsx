/**
 * Document library route. `useSearchParams` requires a Suspense boundary.
 */
import { Suspense } from "react";
import { DocumentLibrary } from "../../../components/documents/document-library";

/**
 * Render the document library, upload, and crawl convenience.
 *
 * @returns Library wrapped in Suspense.
 */
export default function DocumentsPage() {
  return (
    <Suspense fallback={<p>Loading documents</p>}>
      <DocumentLibrary />
    </Suspense>
  );
}
