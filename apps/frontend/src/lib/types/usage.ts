import type { CheckpointUsage } from "../checkpoint-usage";
import type { CostReporting } from "../cost-reporting";
/**
 * Usage and spend OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

export type UsageResponse = {
  scope: string;
  cost_usd: string | number;
  cost_reporting?: CostReporting | null;
  checkpoint_usage?: CheckpointUsage | null;
  display_cost_usd?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  usage_rows: number;
};
