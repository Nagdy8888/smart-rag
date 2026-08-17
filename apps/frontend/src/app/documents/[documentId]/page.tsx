/**
 * Document detail. 404 copy is "Not found" with no title leak.
 */
import { DocumentDetail } from "../../../components/document-detail";

/**
 * Render one document's metadata and ingestion status.
 *
 * @param props - Dynamic `documentId`.
 * @returns Detail surface.
 */
export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ documentId: string }>;
}) {
  const { documentId } = await params;
  return <DocumentDetail documentId={documentId} />;
}
