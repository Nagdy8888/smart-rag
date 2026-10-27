import { describe, expect, it } from "vitest";
import { parseCheckpointUsage, usageDisplayCost } from "./checkpoint-usage";

const history = {runs:2,prompt_tokens:1500,completion_tokens:30,estimated_cost_usd:"0.003",unpriced_runs:0,overlapping_ledger_runs:1,additional_prompt_tokens:1000,additional_completion_tokens:20,additional_estimated_cost_usd:"0.002",first_recorded_at:"2026-10-07T00:00:00Z",last_recorded_at:"2026-10-26T00:00:00Z"};

describe("checkpoint usage reporting",()=>{
  it("preserves stored counters and strips unrelated private fields",()=>{
    expect(parseCheckpointUsage({...history,prompt:"PRIVATE",source_user_id:"PRIVATE"})).toEqual(history);
  });
  it("prefers the deduplicated total to a ledger-only estimate",()=>{
    expect(usageDisplayCost({display_cost_usd:"1.003",cost_reporting:{estimated_cost_usd:"1"}})).toBe("1.003");
    expect(usageDisplayCost({display_cost_usd:null,cost_reporting:{estimated_cost_usd:"88"}})).toBeNull();
  });
  it.each([{...history,prompt_tokens:-1},{...history,runs:true},{...history,estimated_cost_usd:"NaN"},{...history,last_recorded_at:"invalid"}])("rejects malformed recovery totals",row=>{
    expect(()=>parseCheckpointUsage(row)).toThrow();
  });
});
