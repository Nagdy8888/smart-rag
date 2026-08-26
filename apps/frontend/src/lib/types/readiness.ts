/**
 * Readiness and dependency-probe OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** One named probe from authenticated `GET /ops/ready`. */
export type DependencyStatus = {
  name: string;
  status: string;
};

/** Console readiness: public `/health/ready` plus optional operator probes. */
export type ReadinessResponse = {
  status: string;
  query_ready: boolean;
  detail: string;
  rate_limit_degraded: boolean;
  dependencies: DependencyStatus[];
};
