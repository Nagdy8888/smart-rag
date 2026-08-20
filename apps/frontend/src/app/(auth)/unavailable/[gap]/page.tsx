import { UnavailableGap } from "../../../../components/auth/auth-screens";

/**
 * Honest Unavailable page for known missing HTTP (GAP-07-07 / GAP-07-08).
 *
 * @param props - Dynamic `gap` segment.
 * @returns Gap copy with no mocked inputs.
 */
export default async function UnavailablePage({
  params,
}: {
  params: Promise<{ gap: string }>;
}) {
  const { gap } = await params;
  return <UnavailableGap gap={gap} />;
}
