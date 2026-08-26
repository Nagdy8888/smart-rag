/**
 * Usage and spend OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

export type UsageResponse = {
  scope: string;
  cost_usd: string | number;
  prompt_tokens: number;
  completion_tokens: number;
  usage_rows: number;
};
