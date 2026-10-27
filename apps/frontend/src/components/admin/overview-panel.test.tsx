// @vitest-environment jsdom
import { cleanup, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach,beforeEach,describe,it,expect,vi } from "vitest";
import { OverviewPanel } from "./overview-panel";
import { DailyChart, dashboardCost } from "./overview-charts";
import { parseOverview, type Overview } from "../../lib/api/overview";
const api=vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock("../../lib/api/overview",async(importOriginal)=>({...await importOriginal<typeof import("../../lib/api/overview")>(),fetchOverview:api.fetch}));
vi.mock("../../lib/auth/use-api-auth",()=>({useApiAuth:()=>({accessToken:"fixture"})}));
const report = (cost="0") => ({estimated_cost_usd:cost,safety_allowance_usd:"0",budget_accounted_usd:cost,unresolved_operations:0,reconstructed_operations:0,estimated_operations:cost === "0" ? 0 : 1,pricing_basis:"Standard uncached"});
const sample=(): Overview=>({generated_at:"2026-10-26T12:00:00Z",period_start:"2026-09-27T00:00:00Z",days:30,timezone:"UTC",reliability_enabled:false,
  summary:{questions:0,completed:0,failed:0,cancelled:0,measured:0,supported:0,not_measured:0,median_response_seconds:null,latency_samples:0,cost_usd:"0.000001",cost_reporting:report("0.000001")},
  daily:Array.from({length:30},(_,index)=>({date:new Date(Date.UTC(2026,8,27+index)).toISOString().slice(0,10),questions:0,cost_usd:index===29 ? "0.000001":"0",cost_reporting:report(index===29 ? "0.000001":"0")})),
  outcomes:{},authority:{unreviewed:1},authority_unversioned:0,attention_counts:{missing_owner:1},attention_items:[{kind:"missing_owner",source_id:"document",document_id:"document",title:"Handbook"}]});
let client:QueryClient;
beforeEach(()=>{vi.clearAllMocks();api.fetch.mockResolvedValue(sample());client=new QueryClient({defaultOptions:{queries:{retry:false}}});});
afterEach(()=>{cleanup();client.clear();});
function mount(){return render(<QueryClientProvider client={client}><OverviewPanel/></QueryClientProvider>);}
describe("Admin overview",()=>{
  it("uses the combined checkpoint and ledger cost for the summary and chart",async()=>{
    const data=sample();Object.assign(data.summary,{display_cost_usd:"4.56"});Object.assign(data.daily[29],{display_cost_usd:"0.12"});api.fetch.mockResolvedValue(data);
    mount();await screen.findByText("Handbook");
    expect(screen.getByText("Estimated AI cost").nextElementSibling?.textContent).toBe("$4.56");
    expect(screen.getByRole("region",{name:"Estimated usage cost over time"}).textContent).toContain("$0.12");
  });
  it("keeps absent outcomes unmeasured and links only authorized tasks",async()=>{
    mount();await screen.findByText("Handbook");
    expect(screen.getAllByText("Not measured").length).toBeGreaterThan(0);
    expect(within(screen.getByRole("region",{name:"Answer outcomes"})).queryByText("0%")).toBeNull();
    expect(screen.getByText(/Outcome tracking is inactive/)).toBeTruthy();
    expect(screen.getByRole("link",{name:"Handbook"}).getAttribute("href")).toBe("/documents/document");
    expect(screen.getAllByText("$0.000001").length).toBeGreaterThan(0);
  });
  it("never presents safety allowances as spending",async()=>{
    const data=sample();data.summary.cost_usd="88.84";data.summary.cost_reporting={...report("0.12"),budget_accounted_usd:"88.84",safety_allowance_usd:"36.25",unresolved_operations:93,reconstructed_operations:228};api.fetch.mockResolvedValue(data);
    mount();await screen.findByText("Handbook");
    expect(screen.getByText("Estimated AI cost").nextElementSibling?.textContent).toBe("$0.12");
    expect(screen.getByText(/safety allowances are excluded from the estimate/)).toBeTruthy();
    expect(screen.getByText(/93 operations have unresolved charges/)).toBeTruthy();
  });
  it("changes periods and supports explicit refresh",async()=>{
    const user=userEvent.setup();mount();await screen.findByText("Handbook");
    await user.selectOptions(screen.getByLabelText("Reporting period"),"7");
    await waitFor(()=>expect(api.fetch).toHaveBeenCalledWith({accessToken:"fixture"},7));
    await screen.findByText("Handbook");const count=api.fetch.mock.calls.length;
    await user.click(screen.getByRole("button",{name:"Refresh"}));
    await waitFor(()=>expect(api.fetch.mock.calls.length).toBeGreaterThan(count));
  });
  it("shows load failures without inventing a dashboard",async()=>{
    api.fetch.mockRejectedValue(new Error("offline"));mount();
    expect(await screen.findByRole("alert",{}, {timeout:4000})).toBeTruthy();
    expect(screen.queryByText("Questions asked")).toBeNull();
  });
  it("supports keyboard day inspection and a daily table",async()=>{
    const user=userEvent.setup();render(<DailyChart kind="line" label="Activity" points={[{date:"2026-10-25",value:2},{date:"2026-10-26",value:3}]}/>);
    const chart=screen.getByRole("img",{name:/Activity/});chart.focus();await user.keyboard("{Home}");
    expect(screen.getByText("2 questions")).toBeTruthy();await user.keyboard("{ArrowRight}");expect(screen.getByText("3 questions")).toBeTruthy();
    await user.click(screen.getByText("View daily data"));expect(within(screen.getByRole("table")).getByText("2026-10-25")).toBeTruthy();
  });
  it("rejects malformed measurements and preserves tiny recorded costs",()=>{
    expect(parseOverview(sample()).summary.cost_usd).toBe("0.000001");
    expect(()=>parseOverview({...sample(),summary:{...sample().summary,questions:-1}})).toThrow("invalid_overview_response");
    expect(()=>parseOverview({...sample(),daily:[]})).toThrow();
    expect(dashboardCost("0.000001")).toBe("$0.000001");
  });
});
