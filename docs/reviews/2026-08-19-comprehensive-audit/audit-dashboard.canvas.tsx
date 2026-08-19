import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Code2,
  Database,
  FileWarning,
  Gauge,
  ListFilter,
  LockKeyhole,
  Search,
  Server,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

type Severity = "Critical" | "High" | "Medium" | "Low";
type Domain =
  | "Release"
  | "Database"
  | "Security"
  | "Architecture"
  | "Backend"
  | "Frontend"
  | "Operations"
  | "Quality"
  | "Documentation";
type Tab = "overview" | "findings" | "roadmap";

type Finding = {
  id: string;
  severity: Severity;
  domain: Domain;
  title: string;
  evidence: string;
  action: string;
  status: "Open" | "Unverified";
};

const findings: Finding[] = [
  { id: "AUD-C-001", severity: "Critical", domain: "Database", title: "Intended hosted Supabase state was not audited", evidence: "The available connection belongs to another application and is excluded; 59 local migrations are source-only evidence.", action: "Connect the intended project and prove migration, RLS, advisor, Auth, backup, and restore state.", status: "Unverified" },
  { id: "AUD-C-002", severity: "Critical", domain: "Release", title: "Required verification gates are red", evidence: "200 type errors, 7 unit failures, 9 contract failures, 10 unformatted files, plus lint and docs failures.", action: "Restore every release gate without raising baselines or adding release-path skips.", status: "Open" },
  { id: "AUD-C-003", severity: "Critical", domain: "Operations", title: "Managed staging and production are not full-stack qualified", evidence: "Small-host evidence omits worker, ClamAV, parser sandbox, second color, and complete deploy/migration proof.", action: "Run the full immutable stack and prove SSM completion, readiness, smoke, and rollback.", status: "Open" },
  { id: "AUD-C-004", severity: "Critical", domain: "Architecture", title: "Capacity, latency, and recovery claims exceed proof", evidence: "Proof is bounded to 8 versions, 16 chunks, 15 graph docs, 5 query runs, and one API/worker host.", action: "Publish a launch envelope and sign managed load, latency, connection, RTO, and RPO evidence.", status: "Unverified" },
  { id: "AUD-H-001", severity: "High", domain: "Database", title: "Auth-lifecycle tables have grants without RLS", evidence: "revoked_sessions and mfa_recovery_requests grant app_api access without source-level RLS.", action: "Revoke table grants or add deny-by-default forced RLS and narrow RPCs.", status: "Open" },
  { id: "AUD-H-002", severity: "High", domain: "Database", title: "Broad app_api reads bypass ACL intent", evidence: "Several canonical policies use true or deleted-only predicates rather than document ACL.", action: "Prefer RPC-only access or ACL-aware RLS and add negative direct-select tests.", status: "Open" },
  { id: "AUD-H-003", severity: "High", domain: "Database", title: "Core tables do not consistently force RLS", evidence: "Several ingestion, invitation, ledger, and glossary tables enable but do not force RLS.", action: "Force RLS and prove runtime roles never own tenant-sensitive tables.", status: "Open" },
  { id: "AUD-H-004", severity: "High", domain: "Architecture", title: "Parallel retrieval can exceed the connection proof", evidence: "Hybrid channels fan out while pool math covers only one API, one worker, and five runs.", action: "Measure pg_stat_activity under mixed load and bound channel/pool concurrency.", status: "Open" },
  { id: "AUD-H-005", severity: "High", domain: "Backend", title: "Lease loss does not cancel expensive in-flight work", evidence: "Final writes are protected, but parse, embed, and model work can continue to a node boundary.", action: "Propagate cooperative cancellation and test no duplicate external charge.", status: "Open" },
  { id: "AUD-H-006", severity: "High", domain: "Architecture", title: "Graph work has process-wide serialization points", evidence: "A single writer lease/advisory lock and a global adapter lock can grow queue and query latency.", action: "Measure queue age and remove global mutable query state before horizontal scale.", status: "Open" },
  { id: "AUD-H-007", severity: "High", domain: "Operations", title: "Deploy automation does not prove completion", evidence: "The workflow sends SSM work without complete terminal wait, readiness, digest, and rollback proof.", action: "Poll command success, verify candidate health, and auto-restore known-good digests.", status: "Open" },
  { id: "AUD-H-008", severity: "High", domain: "Operations", title: "Restore, alert delivery, and rotation are unproven", evidence: "IaC resources exist, but live acknowledgement, PITR restore, and secret rotation are not evidenced.", action: "Run synthetic alerts, rotation, and a timed canonical plus projection recovery drill.", status: "Unverified" },
  { id: "AUD-H-009", severity: "High", domain: "Quality", title: "Contract tests can silently skip infrastructure", evidence: "About 42 contract files contain dependency-based skip paths.", action: "Create required-stack jobs that fail on unexpected skips or zero test counts.", status: "Open" },
  { id: "AUD-H-010", severity: "High", domain: "Quality", title: "Security-sensitive god files expand blast radius", evidence: "api.ts, Hybrid, LightRAG, query pipeline, SSE, and worker lifecycle concentrate many responsibilities.", action: "After green gates, split by stable concern with characterization tests.", status: "Open" },
  { id: "AUD-H-011", severity: "High", domain: "Frontend", title: "Mobile sign-in is buried below diagnostics", evidence: "At 390×844 the form begins near 1,961 px after nav, readiness, outage, and fixture content.", action: "Use a focused public auth shell and move diagnostics to an authorized route.", status: "Open" },
  { id: "AUD-H-012", severity: "High", domain: "Security", title: "Production CSP permits inline scripts", evidence: "Production script-src intentionally includes unsafe-inline.", action: "Adopt per-request nonce CSP and verify emitted production headers.", status: "Open" },
  { id: "AUD-H-013", severity: "High", domain: "Frontend", title: "Missing Supabase configuration fails open at the UI shell", evidence: "The Next.js proxy continues protected route rendering when public Auth variables are absent.", action: "Fail hosted build/startup and route handling to a dedicated configuration error.", status: "Open" },
  { id: "AUD-H-014", severity: "High", domain: "Frontend", title: "SSE reconnect and async failures are not safely surfaced", evidence: "Only reconnect 404 is classified; other non-OK responses and transport exceptions can become stale state or unhandled rejections.", action: "Classify every response and convert async failures into recoverable UI state.", status: "Open" },
  { id: "AUD-H-015", severity: "High", domain: "Frontend", title: "Missing API origin defaults production clients to localhost", evidence: "NEXT_PUBLIC_API_BASE_URL falls back to 127.0.0.1, which is the end user's machine in a production browser.", action: "Allow localhost only in development and reject missing hosted API configuration.", status: "Open" },
  { id: "AUD-M-001", severity: "Medium", domain: "Database", title: "Ingestion status is a query-heavy polling path", evidence: "Many counts and JSON aggregates run per status request; version indexes need proof.", action: "Add measured indexes and consider an event-maintained status projection.", status: "Open" },
  { id: "AUD-M-002", severity: "Medium", domain: "Database", title: "Large migrations are difficult to review and recover", evidence: "Five migration files exceed roughly 35 KB; one exceeds 1,300 lines.", action: "Keep history immutable; split future DDL, backfill, policy, API, and cleanup concerns.", status: "Open" },
  { id: "AUD-M-003", severity: "Medium", domain: "Database", title: "Pagination uses unnecessary definer privilege", evidence: "The new visible-document page function is definer while related listing functions are invoker.", action: "Use invoker unless negative role tests prove a definer requirement.", status: "Open" },
  { id: "AUD-M-004", severity: "Medium", domain: "Database", title: "Invitation RPC replacement is not expand-contract", evidence: "The old signature is dropped before the new signature is established.", action: "Run old and new signatures in parallel across an application rollout.", status: "Open" },
  { id: "AUD-M-005", severity: "Medium", domain: "Architecture", title: "Valkey transport and memory policy limit scale", evidence: "Per-command TCP behavior combines with a small noeviction limits instance.", action: "Pool/pipeline connections and alert on memory and fallback behavior.", status: "Open" },
  { id: "AUD-M-006", severity: "Medium", domain: "Security", title: "Emergency read limits weaken with replicas", evidence: "Approved-read fallback is process-local when shared stores fail.", action: "Document the degradation or use a durable globally bounded fallback.", status: "Open" },
  { id: "AUD-M-007", severity: "Medium", domain: "Backend", title: "Scanner outages are not a distinct disposition", evidence: "ClamAV outage fails closed but is not separated cleanly from infected content.", action: "Record infected, unavailable, timeout, and unscannable states separately.", status: "Open" },
  { id: "AUD-M-008", severity: "Medium", domain: "Architecture", title: "Query execution state is process-local", evidence: "Resume and cancel assume one active API process.", action: "Keep one active API or move execution ownership into a durable shared store.", status: "Open" },
  { id: "AUD-M-009", severity: "Medium", domain: "Frontend", title: "Signed-out users see protected navigation", evidence: "Nine console destinations render before session and profile resolution.", action: "Render a minimal public shell and role-aware navigation after authorization.", status: "Open" },
  { id: "AUD-M-010", severity: "Medium", domain: "Frontend", title: "Internationalization is fixture-tested, not supported", evidence: "The root remains English/LTR; bidi fixtures do not equal Arabic/RTL product support.", action: "Declare English/LTR scope or implement locale-driven language, direction, and journeys.", status: "Open" },
  { id: "AUD-M-011", severity: "Medium", domain: "Frontend", title: "Accessibility states and destructive UX need tightening", evidence: "Duplicate alert/live announcements, missing feedback pressed state, and immediate deletion remain.", action: "Add one assertive channel, aria-pressed, and confirmation or undo.", status: "Open" },
  { id: "AUD-M-012", severity: "Medium", domain: "Documentation", title: "Documentation enforcement trails policy", evidence: "Index, links, diagrams, size, ownership, and status rules are not all enforced.", action: "Make documentation index and structural policy executable in CI.", status: "Open" },
  { id: "AUD-M-013", severity: "Medium", domain: "Release", title: "Dirty-tree release traceability is weak", evidence: "The pre-report tree had 68 modified and 26 untracked files across runtime and operations.", action: "Create a clean candidate, SBOM, digest manifest, and rerun every gate.", status: "Open" },
  { id: "AUD-M-014", severity: "Medium", domain: "Operations", title: "Health and image scanning are incomplete", evidence: "Worker/Caddy health is shallow, Caddy is tag-pinned, and candidate images lack a scan gate.", action: "Add dependency-aware probes, digest pinning, and Trivy-equivalent scanning.", status: "Open" },
  { id: "AUD-M-015", severity: "Medium", domain: "Security", title: "HSTS is not asserted in repository edge configuration", evidence: "No HSTS policy was found in Next.js, Caddy, or CloudFront IaC; live edge behavior is unverified.", action: "Codify HSTS at the HTTPS edge and test the deployed response.", status: "Unverified" },
  { id: "AUD-M-016", severity: "Medium", domain: "Frontend", title: "Readiness polls every five seconds per open tab", evidence: "Chat and public login issue fixed-interval readiness requests even when stable.", action: "Pause when hidden, back off, and remove operator polling from public auth.", status: "Open" },
  { id: "AUD-L-001", severity: "Low", domain: "Backend", title: "Length-required mutations need client documentation", evidence: "Chunked mutation bodies without numeric Content-Length receive 411.", action: "Document the fail-closed contract or implement bounded streaming.", status: "Open" },
  { id: "AUD-L-002", severity: "Low", domain: "Architecture", title: "The data model assumes one company", evidence: "Profile and graph defaults are single-company, not independent customer tenancy.", action: "Document v1 honestly; require a tenancy ADR before multi-company claims.", status: "Open" },
  { id: "AUD-L-003", severity: "Low", domain: "Security", title: "Worker policies intentionally have broad authority", evidence: "The ingestion worker can affect the full corpus by design.", action: "Treat worker credentials as high impact and keep strict egress/rotation.", status: "Open" },
  { id: "AUD-L-004", severity: "Low", domain: "Frontend", title: "Local dev assets showed stale 403/HMR failures", evidence: "The inspected session logged failed Turbopack chunks and WebSocket handshakes.", action: "Reproduce from a clean dev start and production build before filing a defect.", status: "Unverified" },
  { id: "AUD-L-005", severity: "Low", domain: "Security", title: "API URL safety is delegated to callers", evidence: "The shared helper accepts arbitrary absolute HTTP(S) URLs, though current production calls use path literals.", action: "Reject absolute or off-origin URLs inside the helper.", status: "Open" },
  { id: "AUD-L-006", severity: "Low", domain: "Frontend", title: "Citation and QR URL validation is caller-dependent", evidence: "Citation href and broad data:image QR acceptance rely on caller discipline.", action: "Validate HTTP(S) and required image formats inside the components.", status: "Open" },
  { id: "AUD-L-007", severity: "Low", domain: "Frontend", title: "Invitation acceptance loses a smooth sign-in continuation", evidence: "The route is protected and the login component does not explicitly resume the invitation destination.", action: "Preserve a validated relative destination without exposing the token.", status: "Open" },
];

const severityStyle: Record<Severity, string> = {
  Critical: "border-rose-300 bg-rose-50 text-rose-800",
  High: "border-amber-300 bg-amber-50 text-amber-800",
  Medium: "border-sky-300 bg-sky-50 text-sky-800",
  Low: "border-slate-300 bg-slate-50 text-slate-700",
};

const severityBar: Record<Severity, string> = {
  Critical: "bg-rose-600",
  High: "bg-amber-500",
  Medium: "bg-sky-600",
  Low: "bg-slate-500",
};

const domainIcons: Record<Domain, LucideIcon> = {
  Release: FileWarning,
  Database,
  Security: LockKeyhole,
  Architecture: Gauge,
  Backend: Code2,
  Frontend: Activity,
  Operations: Server,
  Quality: CheckCircle2,
  Documentation: FileWarning,
};

const roadmap = [
  ["0–48 hours", "Freeze release", "Clean candidate, unambiguous environment identity, owners for every blocker."],
  ["Days 1–7", "Restore release truth", "Green format, lint, types, unit, contract, docs, frontend, build, and mandatory-stack runs."],
  ["Week 2", "Harden database and runtime", "Forced RLS, narrow grants, checkpoint secret proof, lease cancellation, measured indexes."],
  ["Weeks 3–4", "Qualify full managed staging", "All services, terminal deploy proof, smoke, alerts, rollback, scanned immutable images."],
  ["Weeks 5–6", "Prove scale and recovery", "Signed envelope, connection/load/latency evidence, failure injection, timed restore."],
  ["Weeks 7–12", "Reduce debt and reassess", "Behavior-neutral god-file splits, documentation ratchets, independent penetration test."],
] as const;

const strengths = [
  "Asymmetric JWT verification and authoritative profile roles",
  "Canonical ACL recheck after derived retrieval",
  "Durable queue leases, ledgers, budgets, and checkpoints",
  "Parser isolation, crawl SSRF controls, and fail-closed scanning",
  "SSE ownership, replay, cancellation, and sanitized errors",
  "Hostile-text rendering and subject-scoped frontend caches",
  "Pinned CI actions and private service networking",
  "171 passing frontend tests and clean frontend types/lint",
];

function MetricCard({ icon: Icon, label, value, note, tone = "navy" }: { icon: LucideIcon; label: string; value: string; note: string; tone?: "navy" | "rose" | "teal" | "amber" }) {
  const tones = {
    navy: "border-slate-200 text-slate-900",
    rose: "border-rose-200 text-rose-800",
    teal: "border-teal-200 text-teal-800",
    amber: "border-amber-200 text-amber-800",
  };
  return (
    <article className={`rounded-2xl border bg-white p-5 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <p className="mt-3 text-3xl font-bold tracking-tight">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{note}</p>
    </article>
  );
}

export default function AuditDashboard() {
  const [tab, setTab] = useState<Tab>("overview");
  const [severity, setSeverity] = useState<Severity | "All">("All");
  const [domain, setDomain] = useState<Domain | "All">("All");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>("AUD-C-001");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return findings.filter((finding) => {
      const severityMatch = severity === "All" || finding.severity === severity;
      const domainMatch = domain === "All" || finding.domain === domain;
      const queryMatch =
        normalized === "" ||
        `${finding.id} ${finding.title} ${finding.evidence} ${finding.action}`
          .toLowerCase()
          .includes(normalized);
      return severityMatch && domainMatch && queryMatch;
    });
  }, [domain, query, severity]);

  const counts = useMemo(
    () =>
      (["Critical", "High", "Medium", "Low"] as Severity[]).map((name) => ({
        name,
        count: findings.filter((item) => item.severity === name).length,
      })),
    [],
  );

  const domains = useMemo(
    () => Array.from(new Set(findings.map((finding) => finding.domain))).sort(),
    [],
  );

  return (
    <main className="min-h-screen bg-[#f3f6fb] text-slate-950">
      <header className="border-b border-slate-800 bg-[#0f1b2d] text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-7 lg:flex-row lg:items-end lg:justify-between lg:px-8">
          <div className="max-w-3xl">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-teal-300">
              <ShieldAlert className="h-5 w-5" aria-hidden="true" />
              Independent comprehensive audit · 19 Aug 2026
            </div>
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Smart RAG production readiness</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
              Production-minded architecture, but release evidence is red or missing at database, integration, deployment, capacity, and recovery boundaries.
            </p>
          </div>
          <div className="rounded-xl border border-rose-400/50 bg-rose-950/40 px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-200">Decision</p>
            <p className="mt-1 text-2xl font-bold text-white">NO-GO</p>
            <p className="mt-1 text-xs text-rose-100">4 independent release blockers</p>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-5 py-6 lg:px-8">
        <section className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Supabase scope corrected</p>
            <p className="mt-1 text-sm leading-6">
              The connected project belongs to another application. Its tables, migrations, and advisors are excluded. Smart RAG database findings are source-level; intended hosted state remains unverified.
            </p>
          </div>
        </section>

        <nav className="mb-6 flex flex-wrap gap-2" aria-label="Audit dashboard sections">
          {([
            ["overview", Activity, "Overview"],
            ["findings", ListFilter, "Findings"],
            ["roadmap", ArrowRight, "Roadmap"],
          ] as const).map(([value, Icon, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              aria-pressed={tab === value}
              className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                tab === value
                  ? "border-[#0f1b2d] bg-[#0f1b2d] text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:border-slate-500"
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        {tab === "overview" ? (
          <div className="space-y-6">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard icon={ShieldAlert} label="Release blockers" value="4 critical" note="Database proof, red gates, incomplete managed stack, and unsupported scale claims." tone="rose" />
              <MetricCard icon={Database} label="Migration surface" value="59 / 86" note="Migration files / declared tables, plus about 170 function statements and 100 indexes." tone="amber" />
              <MetricCard icon={Code2} label="Verification debt" value="200 / 7 / 9" note="Pyright errors / unit failures / contract failures on the dirty candidate." />
              <MetricCard icon={CheckCircle2} label="Frontend signal" value="171 pass" note="Vitest passed with clean frontend TypeScript and ESLint." tone="teal" />
            </section>

            <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2">
                  <Gauge className="h-5 w-5 text-slate-700" aria-hidden="true" />
                  <h2 className="text-lg font-bold">Finding distribution</h2>
                </div>
                <div className="mt-6 space-y-4">
                  {counts.map(({ name, count }) => (
                    <button
                      key={name}
                      type="button"
                      className="grid w-full grid-cols-[76px_1fr_36px] items-center gap-3 text-left"
                      onClick={() => {
                        setSeverity(name);
                        setTab("findings");
                      }}
                    >
                      <span className="text-sm font-semibold text-slate-700">{name}</span>
                      <span className="h-3 overflow-hidden rounded-full bg-slate-100">
                        <span
                          className={`block h-full rounded-full ${severityBar[name]}`}
                          style={{ width: `${Math.max(8, (count / findings.length) * 100)}%` }}
                        />
                      </span>
                      <span className="text-right text-sm font-bold">{count}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-6 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                  The count is not a score. One unverified production database or failed authorization contract can block release regardless of how many positive controls exist.
                </p>
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-teal-700" aria-hidden="true" />
                  <h2 className="text-lg font-bold">Controls worth preserving</h2>
                </div>
                <ul className="mt-5 space-y-3">
                  {strengths.map((strength) => (
                    <li key={strength} className="flex gap-3 text-sm leading-6 text-slate-700">
                      <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-teal-600" aria-hidden="true" />
                      {strength}
                    </li>
                  ))}
                </ul>
              </article>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-slate-700" aria-hidden="true" />
                <h2 className="text-lg font-bold">Evidence boundary</h2>
              </div>
              <div className="mt-5 grid gap-4 md:grid-cols-3">
                {[
                  ["Verified", "Local source, migrations, tests, workflows, documentation, and a public mobile UX inspection."],
                  ["Not verified", "Intended hosted Supabase, managed full stack, production build, live load/latency, restore, and pentest."],
                  ["Working tree", "Commit ed1866d with 68 modified and 26 untracked files before this report was added."],
                ].map(([label, note]) => (
                  <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="font-semibold">{label}</p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{note}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : null}

        {tab === "findings" ? (
          <section>
            <div className="mb-5 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[1fr_auto_auto]">
              <label className="relative">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" aria-hidden="true" />
                <span className="sr-only">Search findings</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search IDs, evidence, or remediation"
                  className="h-10 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-slate-700 focus:ring-2 focus:ring-slate-200"
                />
              </label>
              <select
                aria-label="Filter by severity"
                value={severity}
                onChange={(event) => setSeverity(event.target.value as Severity | "All")}
                className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm"
              >
                <option>All</option>
                <option>Critical</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
              <select
                aria-label="Filter by domain"
                value={domain}
                onChange={(event) => setDomain(event.target.value as Domain | "All")}
                className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm"
              >
                <option>All</option>
                {domains.map((item) => <option key={item}>{item}</option>)}
              </select>
            </div>

            <p className="mb-4 text-sm text-slate-600">{filtered.length} of {findings.length} findings</p>
            <div className="space-y-3">
              {filtered.map((finding) => {
                const DomainIcon = domainIcons[finding.domain];
                const isExpanded = expanded === finding.id;
                return (
                  <article key={finding.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <button
                      type="button"
                      onClick={() => setExpanded(isExpanded ? null : finding.id)}
                      aria-expanded={isExpanded}
                      className="flex w-full items-start gap-4 p-5 text-left"
                    >
                      <span className="rounded-lg bg-slate-100 p-2 text-slate-700">
                        <DomainIcon className="h-5 w-5" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${severityStyle[finding.severity]}`}>{finding.severity}</span>
                          <span className="text-xs font-semibold text-slate-500">{finding.id} · {finding.domain} · {finding.status}</span>
                        </span>
                        <span className="mt-2 block font-bold text-slate-900">{finding.title}</span>
                      </span>
                      {isExpanded ? <ChevronUp className="h-5 w-5 text-slate-500" aria-hidden="true" /> : <ChevronDown className="h-5 w-5 text-slate-500" aria-hidden="true" />}
                    </button>
                    {isExpanded ? (
                      <div className="grid gap-4 border-t border-slate-200 bg-slate-50 p-5 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Evidence</p>
                          <p className="mt-2 text-sm leading-6 text-slate-700">{finding.evidence}</p>
                        </div>
                        <div>
                          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Required action</p>
                          <p className="mt-2 text-sm leading-6 text-slate-700">{finding.action}</p>
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}

        {tab === "roadmap" ? (
          <section className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="space-y-4">
              {roadmap.map(([window, title, exit], index) => (
                <article key={window} className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#0f1b2d] text-sm font-bold text-white">{index + 1}</span>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-teal-700">{window}</p>
                    <h2 className="mt-1 text-lg font-bold">{title}</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{exit}</p>
                  </div>
                </article>
              ))}
            </div>
            <aside className="h-fit rounded-2xl border border-rose-200 bg-white p-6 shadow-sm lg:sticky lg:top-5">
              <ShieldAlert className="h-7 w-7 text-rose-700" aria-hidden="true" />
              <h2 className="mt-4 text-xl font-bold">Production exit rule</h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                The exact candidate must have green gates, intended-database proof, full managed smoke, signed capacity and recovery, tested rollback, and no open critical/high external findings.
              </p>
              <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-900">
                Any missing item keeps the decision at NO-GO.
              </div>
            </aside>
          </section>
        ) : null}
      </div>
    </main>
  );
}
