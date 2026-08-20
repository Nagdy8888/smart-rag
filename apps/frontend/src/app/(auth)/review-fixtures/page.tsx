/**
 * Gated mixed-direction, XSS, and outage-copy fixtures. Not a product journey.
 */
import { SignedOutageCopy } from "../../../components/readiness-panel";
import { ReviewedContentFixtures } from "../../../components/ui/reviewed-content-fixtures";

/**
 * Render reviewed fixtures for zoom/keyboard tests.
 *
 * @returns Fixture panels only.
 */
export default function ReviewFixturesPage() {
  return (
    <>
      <ReviewedContentFixtures />
      <SignedOutageCopy />
    </>
  );
}
