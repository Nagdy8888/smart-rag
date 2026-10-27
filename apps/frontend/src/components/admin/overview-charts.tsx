"use client";
import { useId, useState } from "react";
import styles from "./overview.module.css";

export const dashboardNumber = (value: number) => new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value);
export const dashboardCost = (value: number | string) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: Number(value) !== 0 && Number(value) < .01 ? 8 : 2 }).format(Number(value));
const dayLabel = (date: string) => new Intl.DateTimeFormat("en", {month:"short",day:"numeric",timeZone:"UTC"}).format(new Date(`${date}T00:00:00Z`));

type DailyPoint = { date: string; value: number | null; allowance?: number; unresolved?: number };
/** A single keyboard stop; arrow keys inspect days, with a native table alternative. */
export function DailyChart({ points, kind, label }: { points: DailyPoint[]; kind: "line" | "columns"; label: string }) {
  const [selected, setSelected] = useState<number | null>(null);
  const id = useId();
  const active = selected === null ? points.length - 1 : Math.min(selected, points.length - 1);
  const max = Math.max(...points.map(point => point.value ?? 0), kind === "line" ? 1 : .000001);
  const magnitude = 10 ** Math.floor(Math.log10(max / 4));
  const step = Math.max(1, ([1, 1.5, 2, 2.5, 5, 10].find(factor => factor * magnitude >= max / 4) ?? 10) * magnitude);
  const ceiling = kind === "line" ? step * 4 : max;
  const left = kind === "line" ? 48 : 88;
  const span = 608 - left;
  const x = (index: number) => left + index * span / Math.max(1, points.length - 1);
  const y = (value: number) => 180 - value / ceiling * 152;
  const format = kind === "line" ? dashboardNumber : dashboardCost;
  const chosen = points[active];
  return <div className={styles.chart}>
    <div className={styles.chartReadout} id={`${id}-readout`} aria-live="polite"><span>{chosen ? dayLabel(chosen.date) : "Not measured"}</span><strong>{chosen?.value != null ? format(chosen.value) : "Not measured"}{kind === "line" ? " questions" : chosen?.unresolved ? " (partial)" : ""}</strong></div>
    <svg viewBox="0 0 640 220" role="img" aria-label={`${label}. Use left and right arrow keys to inspect days.`} aria-describedby={`${id}-readout`} tabIndex={0}
      onKeyDown={event=>{ if (["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) { event.preventDefault(); setSelected(event.key === "Home" ? 0 : event.key === "End" ? points.length-1 : Math.max(0,Math.min(points.length-1,active+(event.key === "ArrowLeft" ? -1 : 1)))); } }}>
      {(kind === "line" ? [0,1,2,3,4] : [0,4]).map(tick=><g key={tick}><line x1={left} x2="608" y1={y(ceiling*tick/4)} y2={y(ceiling*tick/4)} className={styles.gridLine}/><text x={left-8} y={y(ceiling*tick/4)+4} textAnchor="end" className={styles.axis}>{format(ceiling*tick/4)}</text></g>)}
      {kind === "line" ? <path d={points.map((point,index)=>point.value === null ? "" : `${index === 0 || points[index-1].value === null ? "M" : "L"}${x(index)},${y(point.value)}`).join(" ")} className={styles.trendLine}/> : points.map((point,index)=>point.value === null ? null : <rect key={point.date} x={x(index)-Math.min(8,200/points.length)} y={y(point.value)} width={Math.min(16,400/points.length)} height={180-y(point.value)} rx="2" className={styles.column}/>)}
      {chosen?.value != null ? <g aria-hidden="true"><line x1={x(active)} x2={x(active)} y1="20" y2="180" className={styles.cursorLine}/><circle cx={x(active)} cy={y(chosen.value)} r="4" className={styles.point}/></g> : null}
      {points.map((point,index)=><rect key={point.date} x={x(index)-span/2/points.length} y="20" width={span/points.length} height="165" fill="transparent" onPointerEnter={()=>setSelected(index)} onPointerDown={()=>setSelected(index)}><title>{dayLabel(point.date)}: {point.value === null ? "Not measured" : format(point.value)}</title></rect>)}
      {[0,Math.floor((points.length-1)/2),points.length-1].filter((n,i,a)=>a.indexOf(n)===i && points[n]).map(index=><text key={index} x={x(index)} y="210" textAnchor={index===0 ? "start" : index===points.length-1 ? "end" : "middle"} className={styles.axis}>{dayLabel(points[index].date)}</text>)}
    </svg>
    <details className={styles.dataDetails}><summary>View daily data</summary><div className={styles.tableScroll}><table><caption>{label} / UTC</caption><thead><tr><th scope="col">Date</th><th scope="col">{kind === "line" ? "Questions" : "Estimated usage cost"}</th>{kind === "columns" ? <><th scope="col">Safety allowance (not spending)</th><th scope="col">Unresolved operations</th></> : null}</tr></thead><tbody>{points.map(point=><tr key={point.date}><th scope="row">{point.date}</th><td>{point.value === null ? "Not measured" : format(point.value)}</td>{kind === "columns" ? <><td>{point.allowance === undefined ? "Unknown" : dashboardCost(point.allowance)}</td><td>{point.unresolved ?? "Unknown"}</td></> : null}</tr>)}</tbody></table></div></details>
  </div>;
}

export function BreakdownChart({ rows, label }: { rows: { label: string; value: number; tone: string }[]; label: string }) {
  const total = rows.reduce((sum,row)=>sum+row.value,0);
  return <div><div className={styles.breakdown} aria-label={label}>{rows.map(row=><div className={styles.breakdownRow} key={row.label}>
    <div className={styles.barLabel}><span>{row.label}</span><span><strong>{dashboardNumber(row.value)}</strong><span className={styles.barPercent}>{total ? `${Math.round(row.value/total*100)}%` : "Not measured"}</span></span></div>
    <div className={styles.barTrack} aria-hidden="true"><span data-tone={row.tone} style={{width:`${total ? row.value/total*100 : 0}%`}} /></div>
  </div>)}</div><details className={styles.dataDetails}><summary>View breakdown data</summary><div className={styles.tableScroll}><table><caption>{label}</caption><thead><tr><th scope="col">Category</th><th scope="col">Count</th><th scope="col">Share</th></tr></thead><tbody>{rows.map(row=><tr key={row.label}><th scope="row">{row.label}</th><td>{dashboardNumber(row.value)}</td><td>{total ? `${Math.round(row.value/total*100)}%` : "Not measured"}</td></tr>)}</tbody></table></div></details></div>;
}
