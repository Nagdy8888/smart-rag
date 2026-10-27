"""Cost-reporting projections are distinct from immutable budget accounting."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CostReporting(BaseModel):
    """Measured/reconstructed estimates with explicit unresolved coverage."""

    model_config = ConfigDict(extra="forbid")
    estimated_cost_usd: Decimal | None = Field(ge=0)
    safety_allowance_usd: Decimal = Field(ge=0)
    unresolved_operations: int = Field(ge=0)
    reconstructed_operations: int = Field(ge=0)
    estimated_operations: int = Field(ge=0)
    budget_accounted_usd: Decimal = Field(ge=0)
    pricing_basis: str = Field(max_length=200)
    measured_prompt_tokens: int | None = Field(default=None, ge=0)
    measured_completion_tokens: int | None = Field(default=None, ge=0)
    unmeasured_operations: int = Field(default=0, ge=0)
