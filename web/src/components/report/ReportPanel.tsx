import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clapperboard,
  FileCheck2,
  Gauge,
  Hash,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";

import type {
  AgentEvent,
  AuditRecord,
  AuditReport,
  Certificate,
  DecisionInfo,
  Finding,
  ImpactEstimate,
} from "@/api-types";
import { CertificateCard } from "@/components/report/CertificateCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import { signedPercent } from "@/lib/arena";
import {
  checkLabel,
  findingTitle,
  heatmapLayout,
  impactSorted,
  narrativePassed,
  narrativeSource,
  orderedFindings,
  reportCounts,
  skepticReviews,
  type HeatmapCell,
  type SkepticReview,
} from "@/lib/report";
import { cn } from "@/lib/utils";

const STATUS_META = {
  kept: {
    label: "KEPT",
    badge: "ok" as const,
    icon: CheckCircle2,
    border: "border-ok/35",
    text: "text-ok",
  },
  rejected: {
    label: "REJECTED",
    badge: "danger" as const,
    icon: XCircle,
    border: "border-danger/35",
    text: "text-danger",
  },
  immaterial: {
    label: "IMMATERIAL",
    badge: "warn" as const,
    icon: AlertTriangle,
    border: "border-warn/35",
    text: "text-warn",
  },
  candidate: {
    label: "CANDIDATE",
    badge: "outline" as const,
    icon: Gauge,
    border: "border-line",
    text: "text-muted",
  },
};

function pValue(value: number): string {
  if (value <= 0) return "p < 1e-300";
  if (value < 0.001) return `p = ${value.toExponential(1)}`;
  return `p = ${value.toFixed(3)}`;
}

function statusLabel(status: Finding["status"]): string {
  return STATUS_META[status].label.toLowerCase();
}

function FindingCard({
  finding,
  review,
}: {
  finding: Finding;
  review?: SkepticReview;
}) {
  const meta = STATUS_META[finding.status];
  const StatusIcon = meta.icon;

  return (
    <article
      className={cn("panel border p-4", meta.border)}
      aria-label={`${meta.label} finding ${findingTitle(finding)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted/60">
            {finding.kind === "intersectional"
              ? "intersectional"
              : "single attribute"}
          </p>
          <h4 className="mt-0.5 text-[14px] font-semibold">
            {findingTitle(finding)}
          </h4>
        </div>
        <Badge variant={meta.badge} className="gap-1">
          <StatusIcon className="h-3 w-3" aria-hidden="true" />
          {meta.label}
        </Badge>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <EvidenceStat label="net flip" value={signedPercent(finding.evidence.net_flip_rate)} tone={meta.text} />
        <EvidenceStat
          label="95% interval"
          value={`${signedPercent(finding.evidence.ci_low)} to ${signedPercent(finding.evidence.ci_high)}`}
        />
        <EvidenceStat label="pairs" value={finding.evidence.n.toLocaleString()} />
        <EvidenceStat label="Holm p" value={pValue(finding.evidence.p_adjusted)} />
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
        <span>
          b={finding.evidence.b} lost · c={finding.evidence.c} gained
        </span>
        <span>observational gap {signedPercent(finding.observational_gap)}</span>
        {finding.matched_evidence && (
          <span>
            income-matched {signedPercent(finding.matched_evidence.net_flip_rate)} ·{" "}
            {finding.matched_evidence.n.toLocaleString()} pairs
          </span>
        )}
      </div>

      <p className="mt-3 text-[11.5px] leading-relaxed text-muted">
        <span className="text-ink">Why: </span>
        {finding.reason || "No Skeptic reason was recorded."}
      </p>

      {review ? (
        <div className="mt-3 border-t border-line/60 pt-3">
          <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted/60">
            Skeptic checks · 6 rules, failures included
          </p>
          <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
            {review.checks.map((check) => (
              <li key={check.name} className="flex items-start gap-1.5">
                {check.passed ? (
                  <CheckCircle2
                    className="mt-0.5 h-3 w-3 shrink-0 text-ok"
                    aria-label="passed"
                  />
                ) : (
                  <XCircle
                    className="mt-0.5 h-3 w-3 shrink-0 text-danger"
                    aria-label="failed"
                  />
                )}
                <span>
                  <span className="text-[10.5px] text-ink">
                    {checkLabel(check.name)}
                  </span>
                  <span className="block font-mono text-[9.5px] leading-snug text-muted/80">
                    {check.detail}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 border-t border-line/60 pt-2 text-[10px] text-muted/60">
          The individual Skeptic checks are no longer in the retained event
          buffer. The persisted verdict is shown above.
        </p>
      )}

      <p className="mt-2 font-mono text-[9px] text-muted/45">{finding.id}</p>
    </article>
  );
}

function EvidenceStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded border border-line/60 bg-canvas/40 px-2 py-1.5">
      <p className="font-mono text-[8.5px] uppercase tracking-[0.12em] text-muted/60">
        {label}
      </p>
      <p className={cn("mt-0.5 font-mono text-[11px]", tone ?? "text-ink")}>
        {value}
      </p>
    </div>
  );
}

function heatBackground(net: number): string {
  const magnitude = Math.min(1, Math.abs(net));
  const alpha = 0.1 + magnitude * 0.7;
  return net >= 0
    ? `rgba(251, 113, 133, ${alpha.toFixed(3)})`
    : `rgba(94, 234, 212, ${alpha.toFixed(3)})`;
}

function heatTextClass(net: number): string {
  return net >= 0 ? "text-[#fff1f3]" : "text-[#04211d]";
}

function HeatCell({ cell }: { cell?: HeatmapCell }) {
  if (!cell) {
    return (
      <td className="rounded border border-line/40 bg-canvas/20 px-2 py-2 text-center font-mono text-[10px] text-muted/40">
        not scanned
      </td>
    );
  }
  return (
    <td
      className={cn("rounded border border-line/40 px-2 py-2", heatTextClass(cell.net))}
      style={{ backgroundColor: heatBackground(cell.net) }}
      title={`${cell.n} pairs · ${pValue(cell.pAdjusted ?? 1)}`}
    >
      <span className="block font-mono text-[11px]">
        {signedPercent(cell.net)}
      </span>
      <span className="block font-mono text-[8.5px] uppercase tracking-[0.1em] opacity-80">
        {cell.status ? statusLabel(cell.status) : "no candidate"}
      </span>
    </td>
  );
}

function Heatmap({ report }: { report: AuditReport }) {
  const layout = heatmapLayout(report);
  const hasCells = layout.rows.length > 0 && layout.genders.length > 0;

  return (
    <section className="panel p-4" aria-label="Intersectional heatmap">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">intersectional scan</p>
          <h3 className="mt-1 text-[15px] font-semibold">
            Where the harm concentrates
          </h3>
          <p className="mt-1 max-w-2xl text-[10.5px] leading-relaxed text-muted">
            Net flip rate by gender, age band, and location. The colour scale is
            fixed at 0–100 percentage points, so a 5 pp cell cannot look as
            alarming as a 60 pp cell.
          </p>
        </div>
        <Badge variant="outline">table fallback included</Badge>
      </div>

      {hasCells ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] border-separate border-spacing-1">
            <caption className="sr-only">
              Intersectional net flip rate in percentage points, with the
              Skeptic verdict for each cell
            </caption>
            <thead>
              <tr>
                <th className="px-2 py-1 text-left font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60">
                  age · location
                </th>
                {layout.genders.map((gender) => (
                  <th
                    key={gender}
                    className="px-2 py-1 text-center font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60"
                  >
                    {gender} target
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {layout.rows.map((row) => (
                <tr key={`${row.ageBand}|${row.urbanRural}`}>
                  <th className="whitespace-nowrap px-2 py-1 text-left font-mono text-[10px] font-normal text-muted">
                    {row.ageBand} · {row.urbanRural}
                  </th>
                  {layout.genders.map((gender) => (
                    <HeatCell key={gender} cell={row.cells[gender]} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[9px] text-muted/70">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-4 rounded-sm bg-[rgba(94,234,212,0.55)]" />
              0 pp
            </span>
            <span>→</span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-4 rounded-sm bg-[rgba(251,113,133,0.8)]" />
              100 pp harm
            </span>
            <span>Each cell shows the paired net flip rate; controls are shown too.</span>
          </div>
        </div>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
          This target was not scanned for intersectional cells. No empty grid is
          invented to fill the space.
        </p>
      )}
    </section>
  );
}

function humanSubgroup(subgroup: string): string {
  return subgroup
    .split(",")
    .map((part) => {
      const token = part.trim();
      const [, value] = token.split("=", 2);
      return value ?? token.replaceAll("_", " ");
    })
    .join(" · ");
}

function ImpactPanel({ impact }: { impact: ImpactEstimate[] }) {
  const estimates = impactSorted(impact);
  const top = estimates[0];

  return (
    <section className="panel p-4" aria-label="Human impact">
      <div className="flex items-center gap-2">
        <Users className="h-4 w-4 text-accent" aria-hidden="true" />
        <div>
          <p className="eyebrow">human impact</p>
          <h3 className="mt-0.5 text-[15px] font-semibold">People per 10,000</h3>
        </div>
      </div>

      {top ? (
        <>
          <p className="mt-3 font-mono text-3xl tracking-tight text-danger">
            {Math.round(top.per_10k).toLocaleString()}
          </p>
          <p className="mt-0.5 text-[10.5px] text-muted">
            people per 10,000 in {humanSubgroup(top.subgroup)}
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted">
            95% range {Math.round(top.ci_low_per_10k).toLocaleString()}–
            {Math.round(top.ci_high_per_10k).toLocaleString()}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-muted">
            {top.explanation}
          </p>
          <p className="mt-2 rounded border border-line/60 bg-canvas/40 px-2 py-1.5 font-mono text-[9.5px] text-muted/75">
            max(net flip rate, 0) × 10,000. No hidden multiplier.
          </p>

          {estimates.length > 1 && (
            <ul className="mt-2 space-y-1">
              {estimates.slice(1).map((estimate) => (
                <li
                  key={estimate.finding_id}
                  className="flex items-baseline justify-between gap-2 border-t border-line/50 pt-1 font-mono text-[10px]"
                >
                  <span className="truncate text-muted">
                    {humanSubgroup(estimate.subgroup)}
                  </span>
                  <span className="shrink-0 text-ink">
                    {Math.round(estimate.per_10k).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="mt-3 rounded-lg border border-dashed border-line/70 px-3 py-4">
          <p className="text-[11px] text-muted">
            No finding survived the Skeptic, so no per-10,000 claim is invented.
          </p>
        </div>
      )}
    </section>
  );
}

function SignOff({
  record,
  onDecided,
  readOnly = false,
}: {
  record: AuditRecord;
  onDecided?: (record: AuditRecord) => void;
  readOnly?: boolean;
}) {
  const [approver, setApprover] = React.useState("");
  const [busy, setBusy] = React.useState<"approve" | "reject" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [issued, setIssued] = React.useState<Certificate | null>(null);
  const [decided, setDecided] = React.useState<DecisionInfo | null>(null);

  const decision = record.decision ?? decided;
  const name = approver.trim();

  const submit = async (choice: "approve" | "reject") => {
    if (!name || busy) return;
    setBusy(choice);
    setError(null);
    try {
      const response = await api.decide(record.id, name, choice);
      setIssued(response.certificate);
      setDecided(response.audit.decision ?? null);
      onDecided?.(response.audit);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "could not record the decision");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel p-4" aria-label="Human sign-off">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
        <div>
          <p className="eyebrow">human gate</p>
          <h3 className="mt-0.5 text-[15px] font-semibold">Sign off</h3>
        </div>
      </div>

      {decision ? (
        <div className="mt-3">
          <Badge variant={decision.decision === "approve" ? "ok" : "danger"}>
            {decision.decision === "approve" ? "approved" : "rejected"}
          </Badge>
          <p className="mt-2 text-[12px] text-ink">{decision.approver}</p>
          <p className="font-mono text-[10px] text-muted">
            certificate #{decision.certificate_index} ·{" "}
            {decision.decided_at}
          </p>
          <p className="mt-2 text-[10.5px] leading-relaxed text-muted">
            {readOnly
              ? "This decision was part of the recording. A replay cannot change it or issue a new certificate."
              : "A named human signed this decision. The certificate is tamper-evident; it does not prove authorship."}
          </p>
        </div>
      ) : readOnly ? (
        <div className="mt-3 rounded-lg border border-dashed border-line/70 px-3 py-4">
          <Badge variant="outline" className="gap-1">
            <Clapperboard className="h-3 w-3" aria-hidden="true" />
            read-only recording
          </Badge>
          <p className="mt-2 text-[10.5px] leading-relaxed text-muted">
            Sign-off is disabled while replaying a recording. Nothing here can
            write a decision or issue a certificate. Use{" "}
            <span className="text-ink">Run again</span> to execute a live audit.
          </p>
        </div>
      ) : (
        <>
          <p className="mt-2 text-[10.5px] leading-relaxed text-muted">
            No certificate without a named human. The auditor does not sign for
            you.
          </p>
          <div className="mt-3 space-y-1.5">
            <Label htmlFor="approver">Approver name</Label>
            <Input
              id="approver"
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
              placeholder="Dr A. Rao"
              autoComplete="name"
            />
          </div>
          {error && (
            <p role="alert" className="mt-2 text-[11px] text-danger">
              {error}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              onClick={() => submit("approve")}
              disabled={!name || busy !== null}
            >
              {busy === "approve" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <FileCheck2 className="h-4 w-4" aria-hidden="true" />
              )}
              Approve & issue certificate
            </Button>
            <Button
              variant="danger"
              onClick={() => submit("reject")}
              disabled={!name || busy !== null}
            >
              {busy === "reject" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <XCircle className="h-4 w-4" aria-hidden="true" />
              )}
              Reject
            </Button>
          </div>
        </>
      )}

      {issued && (
        <div className="mt-3">
          <CertificateCard certificate={issued} />
          <Link
            to="/certificates"
            className="mt-2 inline-flex items-center gap-1 text-[10.5px] text-accent hover:underline"
          >
            Open the certificate chain
            <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </Link>
        </div>
      )}
    </section>
  );
}

function Narrative({ report }: { report: AuditReport }) {
  const narrative = report.narrative?.trim() ?? "";
  if (!narrative) {
    return (
      <section className="panel p-4" aria-label="Narrative">
        <p className="eyebrow">narrative</p>
        <h3 className="mt-1 text-[15px] font-semibold">Report prose</h3>
        <p className="mt-2 text-[11px] text-muted">
          Narrative was not requested for this audit. The computed findings are
          unchanged.
        </p>
      </section>
    );
  }

  const passed = narrativePassed(report);
  return (
    <section className="panel p-4" aria-label="Narrative">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">narrative</p>
          <h3 className="mt-1 text-[15px] font-semibold">
            The computed report, in prose
          </h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={passed ? "ok" : "danger"}>
            {passed ? "number check passed" : "number check failed"}
          </Badge>
          <Badge variant="outline">source: {narrativeSource(report)}</Badge>
        </div>
      </div>
      <p className="mt-3 whitespace-pre-line text-[12px] leading-relaxed text-muted">
        {narrative}
      </p>
      <p className="mt-3 text-[10px] leading-relaxed text-muted/60">
        The LLM only rewrites computed JSON. Every number is checked against the
        report, and a failed draft falls back to the deterministic template.
      </p>
    </section>
  );
}

function ReportActions({
  record,
  mode,
}: {
  record: AuditRecord;
  mode: "live" | "replay";
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const replayable = Boolean(record.target) && !record.target?.startsWith("inline:");
  const recording = record.replay_id;

  const runAgain = async () => {
    if (!replayable || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.startAudit({
        model_id: record.model_id ?? 1,
        target: record.target,
        seed: record.seed,
        include_mitigation: record.include_mitigation,
        include_narrative: record.include_narrative,
      });
      navigate(`/audit/${created.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "could not start the audit");
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {mode === "live" && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => recording && navigate(`/replay/${recording}`)}
            disabled={!recording}
            title={
              recording
                ? "Play the recorded event stream and report. No model is called."
                : "No recording is available for this audit"
            }
          >
            <Clapperboard className="h-3.5 w-3.5" aria-hidden="true" />
            Replay
          </Button>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={runAgain}
          disabled={!replayable || busy}
          title={
            replayable
              ? "Start a new live run against the same target and seed"
              : "A connected endpoint is not stored, so it cannot be run again"
          }
        >
          {busy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Run again
        </Button>
      </div>
      {error && (
        <p role="alert" className="max-w-[240px] text-right text-[10px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export interface ReportPanelProps {
  record: AuditRecord;
  report: AuditReport;
  agentEvents: AgentEvent[];
  mode?: "live" | "replay";
  onDecided?: (record: AuditRecord) => void;
}

export function ReportPanel({
  record,
  report,
  agentEvents,
  mode = "live",
  onDecided,
}: ReportPanelProps) {
  const findings = report.findings ?? [];
  const counts = reportCounts(findings);
  const reviews = React.useMemo(
    () => skepticReviews(agentEvents),
    [agentEvents],
  );

  return (
    <div id="report" className="mt-8 scroll-mt-24">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line/70 pb-3">
        <div>
          <p className="eyebrow">audit report</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-[-0.02em]">
            What survived the Skeptic
          </h2>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <Badge variant="ok">{counts.kept} kept</Badge>
            <Badge variant="danger">{counts.rejected} rejected</Badge>
            {counts.immaterial > 0 && (
              <Badge variant="warn">{counts.immaterial} immaterial</Badge>
            )}
            <span>
              Rejected candidates stay in the report. A materiality miss is not a
              pass.
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/certificates"
            className="inline-flex h-8 items-center gap-1 rounded-md border border-line px-2.5 font-mono text-[10px] text-muted hover:border-accent/45 hover:text-accent"
          >
            <Hash className="h-3 w-3" aria-hidden="true" />
            certificates
          </Link>
          <ReportActions record={record} mode={mode} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,1fr)]">
        <div className="space-y-3">
          {orderedFindings(findings).map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              review={reviews[finding.id]}
            />
          ))}
          {findings.length === 0 && (
            <section className="panel p-4" aria-label="Findings">
              <p className="text-[12px] text-muted">
                No candidate findings were recorded. A null result is not proof
                of fairness.
              </p>
            </section>
          )}
        </div>
        <div className="space-y-4">
          <ImpactPanel impact={report.impact ?? []} />
          <SignOff record={record} onDecided={onDecided} readOnly={mode === "replay"} />
        </div>
      </div>

      <div className="mt-4 grid gap-4">
        <Heatmap report={report} />
        <Narrative report={report} />
      </div>
    </div>
  );
}
