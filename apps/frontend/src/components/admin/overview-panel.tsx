"use client";
import { usageDisplayCost } from "../../lib/checkpoint-usage";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchOverview, type OverviewPeriod } from "../../lib/api/overview";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { sessionCacheScope } from "../../lib/query-keys";
import { KNOWLEDGE_OUTCOME_LABELS } from "../../lib/knowledge-result";
import { UserText } from "../ui/user-text";
import { Button } from "../ui/button";
import { Select } from "../ui/select";
import { Icon } from "../ui/icon";
import { CostReportingDetails } from "./cost-reporting-details";
import { DailyChart, BreakdownChart, dashboardCost, dashboardNumber } from "./overview-charts";
import styles from "./overview.module.css";

const ATTENTION = { conflicting_evidence:"Conflicts to review", feedback:"Feedback reports", insufficient_evidence:"Evidence gaps", overdue_review:"Overdue reviews", missing_owner:"Missing owners" };
const OUTCOMES = ["supported","partial","insufficient_evidence","conflicting_evidence"] as const;
const AUTHORITY = ["approved","unreviewed","draft","superseded"] as const;
const TONES = {supported:"success",partial:"warning",insufficient_evidence:"neutral",conflicting_evidence:"danger",approved:"success",unreviewed:"warning",draft:"neutral",superseded:"muted"};
const time = (seconds: number | null) => seconds === null ? "Not measured" : seconds < 60 ? `${Number(seconds.toFixed(1))}s` : `${Number((seconds/60).toFixed(1))} min`;

export function OverviewPanel() {
  const auth=useApiAuth();
  const [days,setDays]=useState<OverviewPeriod>(30);
  const query=useQuery({queryKey:["admin-overview",sessionCacheScope(auth?.accessToken ?? null),days],queryFn:()=>fetchOverview(auth!,days),enabled:auth!==null,staleTime:60_000,refetchOnWindowFocus:true,retry:1});
  const data=query.data; const summary=data?.summary;
  const attentionTotal=data ? Object.values(data.attention_counts).reduce((sum,n)=>sum+(n ?? 0),0) : 0;
  return <section className={styles.overview} aria-label="Workspace overview">
    <header className={styles.toolbar}><div><h2>Workspace overview</h2><p>Understand activity, evidence, and the knowledge that needs attention.</p><p className={styles.timestamp}>{data ? `Updated ${new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short",timeZone:"UTC"}).format(new Date(data.generated_at))} UTC` : "Reporting timezone: UTC"}{query.isError && data ? " / Last successful snapshot" : ""}</p></div>
      <div className={styles.toolbarActions}><Select label="Reporting period" data-action-id="admin.overview.period" value={String(days)} options={[7,30,90].map(value=>({value:String(value),label:`Last ${value} days`}))} onChange={event=>setDays(Number(event.target.value) as OverviewPeriod)}/><Button variant="secondary" data-action-id="admin.overview.refresh" pending={query.isFetching} pendingLabel="Refreshing" onClick={()=>void query.refetch()}>Refresh</Button></div>
    </header>
    {query.isError ? <div role="alert" className={styles.error}>Overview could not be refreshed. {data ? "The last successful snapshot is shown." : "Check the connection and try Refresh."}</div> : null}
    {query.isPending ? <div role="status" className={styles.loading}><Icon name="clock" aria-hidden="true"/><p>Loading your workspace overview...</p></div> : null}
    {data && summary ? <>
      {!data.reliability_enabled ? <div className={styles.notice}><Icon name="help" aria-hidden="true"/><p>Outcome tracking is inactive while reliability mode is disabled. Previously recorded outcomes remain visible; historical answers are not scored retroactively.</p></div> : null}
      <dl className={styles.metrics}>
        <div><dt>Questions asked</dt><dd>{dashboardNumber(summary.questions)}</dd><p>Admitted questions / last {days} days</p></div>
        <div><dt>Supported answers</dt><dd>{summary.measured ? `${Math.round(summary.supported/summary.measured*100)}%` : "Not measured"}</dd><p>{dashboardNumber(summary.supported)} of {dashboardNumber(summary.measured)} recorded outcomes</p></div>
        <div><dt>Typical response time</dt><dd>{time(summary.median_response_seconds)}</dd><p>Median including queue / {dashboardNumber(summary.latency_samples)} completed runs</p></div>
        <div><dt>Estimated AI cost</dt><dd>{usageDisplayCost(summary) != null ? dashboardCost(usageDisplayCost(summary)!) : "Not measured"}</dd><p>{summary.cost_reporting?.unresolved_operations ? "Partial estimate / unresolved charges excluded" : "Query, ingestion and recovered checkpoint estimates / USD"}</p></div>
      </dl>
      <div className={styles.mainGrid}>
        <section className={`${styles.panel} ${styles.activity}`} aria-label="Questions over time"><header className={styles.panelHeader}><div><h3>Questions over time</h3><p>How often people turn to the assistant.</p></div><span className={styles.period}>{days} days / UTC</span></header>
          {summary.questions===0 ? <p className={styles.empty}>No questions in this period. Activity appears here after someone asks the assistant.</p> : null}
          <DailyChart label="Questions over time" kind="line" points={data.daily.map(day=>({date:day.date,value:day.questions}))}/>
          <footer className={styles.chartFooter}><span><strong>{dashboardNumber(summary.failed)}</strong> failed</span><span><strong>{dashboardNumber(summary.cancelled)}</strong> cancelled</span><span>Counted separately from answer outcomes</span></footer>
        </section>
        <section className={`${styles.panel} ${styles.attention}`} aria-label="Needs attention"><header className={styles.panelHeader}><div><h3>Needs attention</h3><p>Open items you have permission to review.</p></div><span className={styles.total}>{dashboardNumber(attentionTotal)}</span></header>
          <dl className={styles.attentionCounts}>{Object.entries(ATTENTION).map(([kind,label])=><div key={kind}><dt>{label}</dt><dd>{dashboardNumber(data.attention_counts[kind as keyof typeof ATTENTION] ?? 0)}</dd></div>)}</dl>
          {data.attention_items.length ? <ul className={styles.attentionList}>{data.attention_items.map(item=><li key={`${item.kind}:${item.source_id}`}><span>{ATTENTION[item.kind]}</span><Link href={item.document_id ? `/documents/${encodeURIComponent(item.document_id)}` : "/admin?tab=knowledge"}><UserText value={item.title ?? ATTENTION[item.kind]}/></Link></li>)}</ul> : <div className={styles.empty}><Icon name="checkCircle" aria-hidden="true"/><p>No open items visible to you. Source permissions and review consent still apply.</p></div>}
          <Link className={styles.link} href="/admin?tab=knowledge">Open Knowledge maintenance<Icon name="chevron" aria-hidden="true"/></Link>
        </section>
      </div>
      <div className={styles.secondaryGrid}>
        <section className={styles.panel} aria-label="Answer outcomes"><header className={styles.panelHeader}><div><h3>Answer outcomes</h3><p>What the available evidence could support.</p></div></header>
          <BreakdownChart label="Recorded answer outcomes" rows={OUTCOMES.map(key=>({label:KNOWLEDGE_OUTCOME_LABELS[key],value:data.outcomes[key] ?? 0,tone:TONES[key]}))}/>
          <p className={styles.footnote}>{summary.measured ? `${dashboardNumber(summary.measured)} recorded outcomes.` : "Not measured: no knowledge outcomes were recorded in this period."} Evidence support is not independently verified correctness.</p>
          <p className={styles.footnote}><strong>{dashboardNumber(summary.not_measured)} completed runs not measured.</strong> Failed and cancelled runs are excluded from this label.</p>
        </section>
        <section className={styles.panel} aria-label="Document authority"><header className={styles.panelHeader}><div><h3>Document authority</h3><p>Current versions of documents you can access.</p></div><span className={styles.period}>Current snapshot</span></header>
          <BreakdownChart label="Current document authority" rows={AUTHORITY.map(key=>({label:key.charAt(0).toUpperCase()+key.slice(1),value:data.authority[key] ?? 0,tone:TONES[key]}))}/>
          <p className={styles.footnote}>Approval alone does not establish whether a policy applies today. This snapshot is unaffected by the period selector.{data.authority_unversioned ? ` ${dashboardNumber(data.authority_unversioned)} documents have no current version.` : ""}</p>
          <Link className={styles.link} href="/documents">Open document library<Icon name="chevron" aria-hidden="true"/></Link>
        </section>
      </div>
      <section className={styles.panel} aria-label="Estimated usage cost over time"><header className={styles.panelHeader}><div><h3>Estimated usage cost over time</h3><p>Token-based estimates; safety allowances are excluded.</p></div><Link className={styles.link} href="/admin?tab=usage">View Usage<Icon name="chevron" aria-hidden="true"/></Link></header>
        <DailyChart label="Estimated usage cost over time" kind="columns" points={data.daily.map(day=>({date:day.date,value:usageDisplayCost(day) != null ? Number(usageDisplayCost(day)) : null,allowance:Number(day.cost_reporting?.safety_allowance_usd ?? 0),unresolved:day.cost_reporting?.unresolved_operations ?? 0}))}/>
        <CostReportingDetails report={summary.cost_reporting} />
        {summary.checkpoint_usage?.runs ? <p className={styles.footnote}>{dashboardNumber(summary.checkpoint_usage.runs)} checkpoint runs are included in this period. Ledger overlaps are counted once; missing or allowance-like stored costs are excluded.</p> : null}
      </section>
    </> : null}
  </section>;
}
