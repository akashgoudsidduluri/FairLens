import * as React from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  FileText,
  RefreshCw,
  Scale,
  XCircle,
} from "lucide-react";

import type {
  EvidenceReport,
  RealModelEvidence,
  SandboxModelEvidence,
  SuiteBModelEvidence,
} from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton, LoadingLine, Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";

function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function decimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(digits);
}

function expectationVariant(
  row: SandboxModelEvidence,
): "ok" | "danger" | "outline" {
  if (row.expectation_total === 0) return "outline";
  return row.expectation_passed === row.expectation_total ? "ok" : "danger";
}

function SourceStrip({ sources }: { sources: { path: string; present: boolean }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-1.5">
      {sources.map((source) => (
        <li key={source.path}>
          <Badge
            variant={source.present ? "outline" : "danger"}
            className="max-w-full gap-1 whitespace-normal text-left"
          >
            {source.present ? (
              <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
            ) : (
              <XCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
            )}
            <span className="break-all font-mono">{source.path}</span>
            {!source.present && <span>missing</span>}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-line/60 bg-canvas/40 px-3 py-2">
      <p className="font-mono text-[8.5px] uppercase tracking-[0.13em] text-muted/70">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-[15px] text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-[9.5px] leading-snug text-muted/70">{hint}</p>}
    </div>
  );
}

function SandboxTable({ rows }: { rows: SandboxModelEvidence[] }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <caption className="sr-only">
          Sandbox validation: pre-registered expectation, kept findings, and
          false alarms before and after the Skeptic
        </caption>
        <thead>
          <tr className="border-b border-line/70 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70">
            <th className="px-2 py-2 font-normal">model</th>
            <th className="px-2 py-2 font-normal">runs</th>
            <th className="px-2 py-2 font-normal">pre-registered</th>
            <th className="px-2 py-2 font-normal">kept findings</th>
            <th className="px-2 py-2 font-normal">false alarms before → after</th>
            <th className="px-2 py-2 font-normal">number check</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.model_id} className="border-b border-line/40 align-top">
              <td className="px-2 py-2.5 text-[12px] text-ink">
                Model {row.model_id}
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] text-muted">
                {row.runs}
              </td>
              <td className="px-2 py-2.5">
                <Badge variant={expectationVariant(row)}>
                  {row.expectation_total === 0
                    ? "no expectation"
                    : `${row.expectation_passed}/${row.expectation_total} met`}
                </Badge>
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] text-ink">
                {decimal(row.kept_mean)}
                <span className="text-muted">
                  {" "}
                  ({row.kept_min}–{row.kept_max})
                </span>
              </td>
              <td className="px-2 py-2.5">
                {(row.false_alarm_runs ?? 0) > 0 ? (
                  <span className="font-mono text-[11px] text-ink">
                    {row.false_alarm_before ?? 0} → {row.false_alarm_after ?? 0}
                    <span className="ml-1.5 text-[9.5px] text-muted">
                      over {row.false_alarm_runs ?? 0} runs
                    </span>
                  </span>
                ) : (
                  <span className="font-mono text-[10px] text-muted/70">
                    not recorded
                  </span>
                )}
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] text-muted">
                {row.number_check_passed}/{row.runs}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreRegistrationMisses({ rows }: { rows: SandboxModelEvidence[] }) {
  const missed = rows.filter(
    (row) => row.expectation_total > 0 && row.expectation_passed === 0,
  );

  if (missed.length === 0) {
    return (
      <p className="mt-3 flex items-center gap-2 text-[11.5px] text-ok">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        Every model met its pre-registered expectation.
      </p>
    );
  }

  return (
    <div className="mt-3 space-y-2">
      {missed.map((row) => (
        <div
          key={row.model_id}
          role="alert"
          className="rounded-lg border border-warn/35 bg-warn/[0.055] p-3"
        >
          <p className="flex items-center gap-2 text-[12px] font-semibold text-warn">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Model {row.model_id} missed its pre-registration.
          </p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-ink">
            {row.expectation_passed} of {row.expectation_total} seeds met the
            stated expectation. The miss is reported here rather than hidden by a
            threshold change after the result was seen.
          </p>
          {row.misses.length > 0 && (
            <ul className="mt-2 space-y-1">
              {row.misses.map((miss) => (
                <li key={miss} className="font-mono text-[10.5px] leading-relaxed text-muted">
                  {miss}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function SuiteBTable({ rows }: { rows: SuiteBModelEvidence[] }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[880px] border-collapse text-left">
        <caption className="sr-only">
          Suite B: planted treatment and context, kept findings, discovery and
          confirmation counts, MDE, and the Fairlearn gap on the same data
        </caption>
        <thead>
          <tr className="border-b border-line/70 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70">
            <th className="px-2 py-2 font-normal">model</th>
            <th className="px-2 py-2 font-normal">pre-registered</th>
            <th className="px-2 py-2 font-normal">kept findings</th>
            <th className="px-2 py-2 font-normal">cells · candidates → confirmed</th>
            <th className="px-2 py-2 font-normal">false alarms before → after</th>
            <th className="px-2 py-2 font-normal">MDE n=200</th>
            <th className="px-2 py-2 font-normal">largest Fairlearn DP</th>
            <th className="px-2 py-2 font-normal">runtime</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const met =
              row.expectation_total > 0 &&
              row.expectation_passed === row.expectation_total;
            return (
              <tr key={row.model_id} className="border-b border-line/40 align-top">
                <td className="px-2 py-2.5 text-[12px] text-ink">
                  {row.model_id === 15 ? "Control 15" : `Model ${row.model_id}`}
                </td>
                <td className="px-2 py-2.5">
                  <Badge variant={met ? "ok" : "danger"}>
                    {row.expectation_passed}/{row.expectation_total} met
                  </Badge>
                </td>
                <td className="px-2 py-2.5 font-mono text-[11px] text-ink">
                  {decimal(row.kept_mean)}
                  <span className="text-muted">
                    {" "}
                    ({row.kept_min}–{row.kept_max})
                  </span>
                </td>
                <td className="px-2 py-2.5 font-mono text-[10.5px] text-muted">
                  {row.cells_examined} · {decimal(row.candidates_mean)} →{" "}
                  {decimal(row.confirmed_mean)}
                </td>
                <td className="px-2 py-2.5 font-mono text-[11px] text-ink">
                  {row.false_alarm_before ?? 0} → {row.false_alarm_after ?? 0}
                  <span className="ml-1 text-[9.5px] text-muted">
                    over {row.runs} runs
                  </span>
                </td>
                <td className="px-2 py-2.5 font-mono text-[10.5px] text-muted">
                  {row.mde_n200 === null || row.mde_n200 === undefined
                    ? "—"
                    : row.mde_n200.toFixed(3)}
                </td>
                <td className="px-2 py-2.5 font-mono text-[10.5px] text-muted">
                  {row.max_dp_gap === null || row.max_dp_gap === undefined
                    ? "—"
                    : `${percent(row.max_dp_gap)} (${row.max_dp_attribute})`}
                </td>
                <td className="px-2 py-2.5 font-mono text-[10.5px] text-muted">
                  {row.runtime_mean_s.toFixed(1)}s
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type ProtocolTotals = {
  runs: number;
  keptMean: number;
  keptMin: number;
  keptMax: number;
  passed: number;
  total: number;
  falseAlarmBefore: number;
  falseAlarmAfter: number;
};

function protocolTotals(rows: SuiteBModelEvidence[]): ProtocolTotals {
  const runs = rows.reduce((sum, row) => sum + row.runs, 0);
  const kept = rows.reduce((sum, row) => sum + row.kept_mean * row.runs, 0);
  return {
    runs,
    keptMean: runs > 0 ? kept / runs : 0,
    keptMin: rows.length > 0 ? Math.min(...rows.map((row) => row.kept_min)) : 0,
    keptMax: rows.length > 0 ? Math.max(...rows.map((row) => row.kept_max)) : 0,
    passed: rows.reduce((sum, row) => sum + row.expectation_passed, 0),
    total: rows.reduce((sum, row) => sum + row.expectation_total, 0),
    falseAlarmBefore: rows.reduce(
      (sum, row) => sum + (row.false_alarm_before ?? 0),
      0,
    ),
    falseAlarmAfter: rows.reduce(
      (sum, row) => sum + (row.false_alarm_after ?? 0),
      0,
    ),
  };
}

function SuiteBComparison({
  p1,
  p2,
}: {
  p1: SuiteBModelEvidence[];
  p2: SuiteBModelEvidence[];
}) {
  const p1ById = new Map(p1.map((row) => [row.model_id, row]));
  const p2ById = new Map(p2.map((row) => [row.model_id, row]));
  const ids = Array.from(
    new Set([...p1.map((row) => row.model_id), ...p2.map((row) => row.model_id)]),
  ).sort((left, right) => left - right);
  const total1 = protocolTotals(p1);
  const total2 = protocolTotals(p2);

  return (
    <>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Stat
          label="expectations met"
          value={`${total1.passed}/${total1.total} → ${total2.passed}/${total2.total}`}
          hint="protocol 1 → protocol 2"
        />
        <Stat
          label="kept findings per audit"
          value={`${decimal(total1.keptMean)} → ${decimal(total2.keptMean)}`}
          hint={`range ${total1.keptMin}–${total1.keptMax} → ${total2.keptMin}–${total2.keptMax}`}
        />
        <Stat
          label="false alarms after Skeptic"
          value={`${total1.falseAlarmAfter} → ${total2.falseAlarmAfter}`}
          hint={`before the Skeptic: ${total1.falseAlarmBefore} in protocol 1, ${total2.falseAlarmBefore} in protocol 2`}
        />
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[820px] border-collapse text-left">
          <caption className="sr-only">
            Protocol 1 next to protocol 2: kept findings, met expectations, and
            false alarms before and after the Skeptic
          </caption>
          <thead>
            <tr className="border-b border-line/70 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70">
              <th className="px-2 py-2 font-normal">model</th>
              <th className="px-2 py-2 font-normal">P1 kept</th>
              <th className="px-2 py-2 font-normal">P1 met</th>
              <th className="px-2 py-2 font-normal">P2 kept</th>
              <th className="px-2 py-2 font-normal">P2 met</th>
              <th className="px-2 py-2 font-normal">P1 false alarms</th>
              <th className="px-2 py-2 font-normal">P2 false alarms</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((modelId) => {
              const first = p1ById.get(modelId);
              const second = p2ById.get(modelId);
              return (
                <tr key={modelId} className="border-b border-line/40 align-top">
                  <td className="px-2 py-2.5 text-[12px] text-ink">
                    {modelId === 15 ? "Control 15" : `Model ${modelId}`}
                  </td>
                  <td className="px-2 py-2.5 font-mono text-[11px] text-ink">
                    {first
                      ? `${decimal(first.kept_mean)} (${first.kept_min}–${first.kept_max})`
                      : "—"}
                  </td>
                  <td className="px-2 py-2.5">
                    {first ? (
                      <Badge
                        variant={
                          first.expectation_total > 0 &&
                          first.expectation_passed === first.expectation_total
                            ? "ok"
                            : "danger"
                        }
                      >
                        {first.expectation_passed}/{first.expectation_total}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-2.5 font-mono text-[11px] text-ink">
                    {second
                      ? `${decimal(second.kept_mean)} (${second.kept_min}–${second.kept_max})`
                      : "—"}
                  </td>
                  <td className="px-2 py-2.5">
                    {second ? (
                      <Badge
                        variant={
                          second.expectation_total > 0 &&
                          second.expectation_passed === second.expectation_total
                            ? "ok"
                            : "danger"
                        }
                      >
                        {second.expectation_passed}/{second.expectation_total}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-2.5 font-mono text-[11px] text-muted">
                    {first
                      ? `${first.false_alarm_before ?? 0} → ${first.false_alarm_after ?? 0}`
                      : "—"}
                  </td>
                  <td className="px-2 py-2.5 font-mono text-[11px] text-muted">
                    {second
                      ? `${second.false_alarm_before ?? 0} → ${second.false_alarm_after ?? 0}`
                      : "—"}
                  </td>
                </tr>
              );
            })}
            <tr className="border-t border-line/70 bg-canvas/30 align-top">
              <td className="px-2 py-2.5 text-[12px] font-semibold text-ink">
                All
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] font-semibold text-ink">
                {decimal(total1.keptMean)} ({total1.keptMin}–{total1.keptMax})
              </td>
              <td className="px-2 py-2.5">
                <Badge
                  variant={
                    total1.total > 0 && total1.passed === total1.total
                      ? "ok"
                      : "danger"
                  }
                >
                  {total1.passed}/{total1.total}
                </Badge>
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] font-semibold text-ink">
                {decimal(total2.keptMean)} ({total2.keptMin}–{total2.keptMax})
              </td>
              <td className="px-2 py-2.5">
                <Badge
                  variant={
                    total2.total > 0 && total2.passed === total2.total
                      ? "ok"
                      : "danger"
                  }
                >
                  {total2.passed}/{total2.total}
                </Badge>
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] font-semibold text-ink">
                {total1.falseAlarmBefore} → {total1.falseAlarmAfter}
              </td>
              <td className="px-2 py-2.5 font-mono text-[11px] font-semibold text-ink">
                {total2.falseAlarmBefore} → {total2.falseAlarmAfter}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

function SuiteBMisses({ rows }: { rows: SuiteBModelEvidence[] }) {
  const reported = rows.filter(
    (row) => row.misses.length > 0 || row.notes.length > 0,
  );
  if (reported.length === 0) {
    return (
      <p className="mt-3 flex items-center gap-2 text-[11.5px] text-ok">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        Every suite B model met its pre-registered pass criteria, with no notes.
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-2">
      {reported.map((row) => (
        <div
          key={row.model_id}
          className="rounded-lg border border-warn/35 bg-warn/[0.045] p-3"
        >
          <p className="flex items-center gap-2 text-[12px] font-semibold text-warn">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            {row.model_id === 15 ? "Control 15" : `Model ${row.model_id}`}
            {row.misses.length > 0 ? " missed a criterion" : " has a reported note"}
          </p>
          {row.misses.length > 0 && (
            <ul className="mt-2 space-y-1">
              {row.misses.map((miss) => (
                <li
                  key={miss}
                  className="font-mono text-[10.5px] leading-relaxed text-muted"
                >
                  MISS · {miss}
                </li>
              ))}
            </ul>
          )}
          {row.notes.length > 0 && (
            <ul className="mt-2 space-y-1">
              {row.notes.map((note) => (
                <li
                  key={note}
                  className="font-mono text-[10.5px] leading-relaxed text-muted"
                >
                  note · {note}
                </li>
              ))}
            </ul>
          )}
          {row.kept_ids.length > 0 && (
            <p className="mt-2 font-mono text-[9.5px] text-muted/80">
              kept: {row.kept_ids.join(", ")}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function RealModelCard({ model }: { model: RealModelEvidence }) {
  return (
    <article className="panel p-4" aria-label={`${model.label} evidence`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">real dataset · {model.model}</p>
          <h3 className="mt-1 text-[16px] font-semibold">{model.label}</h3>
          <p className="mt-0.5 font-mono text-[10px] text-muted">
            {model.runs} runs · probes: {model.supported_probes.join(", ") || "none"}
          </p>
        </div>
        <Badge variant="outline">
          {model.skipped_probes.length} unsupported probe
          {model.skipped_probes.length === 1 ? "" : "s"} skipped
        </Badge>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="FairLens verdicts"
          value={`${decimal(model.kept_mean)} kept`}
          hint={`${decimal(model.rejected_mean)} rejected · ${decimal(model.immaterial_mean)} immaterial per run`}
        />
        <Stat
          label="human impact"
          value={
            model.impact_per_10k_mean === null || model.impact_per_10k_mean === undefined
              ? "—"
              : `${Math.round(model.impact_per_10k_mean).toLocaleString()} / 10k`
          }
          hint={
            model.impact_per_10k_min !== null &&
            model.impact_per_10k_min !== undefined &&
            model.impact_per_10k_max !== null &&
            model.impact_per_10k_max !== undefined
              ? `${Math.round(model.impact_per_10k_min).toLocaleString()}–${Math.round(model.impact_per_10k_max).toLocaleString()} across seeds`
              : undefined
          }
        />
        <Stat label="holdout accuracy" value={percent(model.holdout_accuracy)} />
        <Stat label="holdout AUC" value={percent(model.holdout_auc)} />
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left">
          <caption className="sr-only">
            Fairlearn disparity metrics next to the FairLens verdict for {model.label}
          </caption>
          <thead>
            <tr className="border-b border-line/70 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70">
              <th className="px-2 py-1.5 font-normal">attribute</th>
              <th className="px-2 py-1.5 font-normal">Fairlearn DP difference</th>
              <th className="px-2 py-1.5 font-normal">Fairlearn EO difference</th>
            </tr>
          </thead>
          <tbody>
            {model.fairlearn.map((metric) => (
              <tr key={metric.attribute} className="border-b border-line/40">
                <td className="px-2 py-1.5 text-[11.5px] text-ink">
                  {metric.attribute}
                </td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-muted">
                  {percent(metric.demographic_parity_difference)}
                </td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-muted">
                  {percent(metric.equalized_odds_difference)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-[10px] leading-relaxed text-muted/70">
        Fairlearn measures outcomes on the dataset's own population. FairLens
        probes the synthetic generator mapped into the dataset's columns. The
        columns answer different questions and are shown side by side, not as a
        validation of each other.
      </p>

      {model.notes.length > 0 && (
        <details className="mt-3 rounded-lg border border-line/60 bg-canvas/30 px-3 py-2">
          <summary className="cursor-pointer font-mono text-[10px] text-muted hover:text-accent">
            What FairLens reported ({model.notes.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {model.notes.map((note) => (
              <li key={note} className="font-mono text-[10px] leading-relaxed text-muted">
                {note}
              </li>
            ))}
          </ul>
        </details>
      )}

      {model.errors.length > 0 && (
        <div role="alert" className="mt-3 rounded border border-danger/30 bg-danger/[0.04] px-3 py-2">
          <p className="font-mono text-[10px] text-danger">
            {model.errors.join(" · ")}
          </p>
        </div>
      )}
    </article>
  );
}

export function Evidence() {
  const [evidence, setEvidence] = React.useState<EvidenceReport | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api
      .getEvidence()
      .then((value) => {
        if (!active) return;
        setEvidence(value);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(
          cause instanceof ApiError ? cause.detail : "could not read the evaluation results",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  if (loading) {
    return <EvidenceLoading />;
  }

  if (error || !evidence) {
    return (
      <div className="mx-auto w-full max-w-[900px] px-5 py-20">
        <p className="eyebrow">evidence</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-[-0.02em]">
          The evaluation results could not be read
        </h1>
        <div role="alert" className="mt-4 rounded-lg border border-danger/30 bg-danger/[0.04] p-4">
          <p className="text-[12px] text-danger">{error ?? "empty evidence payload"}</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="mt-4"
          onClick={() => setAttempt((value) => value + 1)}
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  const sandbox = evidence.sandbox;
  const real = evidence.real;
  const suiteB = evidence.suite_b;
  const suiteBR51 = evidence.suite_b_r51;
  const hasProtocolComparison =
    suiteB.models.length > 0 && suiteBR51.models.length > 0;
  const falseAlarmMeasured =
    sandbox.false_alarm_before !== null && sandbox.false_alarm_after !== null;
  const misses = sandbox.models.filter(
    (row) => row.expectation_total > 0 && row.expectation_passed === 0,
  );

  return (
    <div className="mx-auto w-full max-w-[1400px] px-5 pb-24 pt-8">
      <p className="eyebrow">evidence</p>
      <h1 className="mt-1 max-w-3xl text-3xl font-semibold tracking-[-0.03em]">
        What the evaluation actually found
      </h1>
      <p className="mt-2 max-w-3xl text-[12px] leading-relaxed text-muted">
        Every number on this page is computed by the API from the committed
        result files. Nothing is typed into the UI. Generated{" "}
        <span className="font-mono text-[10.5px] text-ink">
          {evidence.generated_at}
        </span>
        .
      </p>

      <section className="mt-8" aria-labelledby="sandbox-heading">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line/70 pb-3">
          <div>
            <p className="eyebrow">sandbox validation</p>
            <h2 id="sandbox-heading" className="mt-1 text-xl font-semibold tracking-[-0.02em]">
              Expected vs found
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-muted">
              Seven planted models, five seeds each. The expectation was frozen
              before the first audit; a miss is reported, not re-thresholded.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={sandbox.expectation_passed === sandbox.expectation_total ? "ok" : "danger"}>
              {sandbox.expectation_passed}/{sandbox.expectation_total} expectations met
            </Badge>
            <Badge variant="outline">{sandbox.runs} audits</Badge>
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="expectations met"
            value={`${sandbox.expectation_passed} / ${sandbox.expectation_total}`}
            hint="pre-registered before the first audit"
          />
          <Stat
            label="false alarms before Skeptic"
            value={falseAlarmMeasured ? decimal(sandbox.false_alarm_before) : "—"}
            hint={
              falseAlarmMeasured
                ? "across models with a recorded false-alarm check"
                : "not recorded in these results"
            }
          />
          <Stat
            label="false alarms after Skeptic"
            value={falseAlarmMeasured ? decimal(sandbox.false_alarm_after) : "—"}
            hint={falseAlarmMeasured ? "survivors of all six checks" : undefined}
          />
          <Stat
            label="models that missed"
            value={String(misses.length)}
            hint={
              misses.length > 0
                ? misses.map((row) => `model ${row.model_id}`).join(", ")
                : "none"
            }
          />
        </div>

        <SandboxTable rows={sandbox.models} />
        <PreRegistrationMisses rows={sandbox.models} />
        <div className="mt-3">
          <SourceStrip sources={sandbox.sources} />
        </div>
      </section>

      <section className="mt-10" aria-labelledby="suite-b-heading">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line/70 pb-3">
          <div>
            <p className="eyebrow">validation suite B · two pre-registered protocols</p>
            <h2
              id="suite-b-heading"
              className="mt-1 flex items-center gap-2 text-xl font-semibold tracking-[-0.02em]"
            >
              <BarChart3 className="h-4 w-4 text-accent" aria-hidden="true" />
              Treatment × context, discovered then confirmed
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-muted">
              Models 8–14 plant an effect in a specific treatment and context;
              Model 15 is the clean control. Each audit ran the same 110-cell
              discovery panel, Holm across every cell, then 400 fresh pairs per
              candidate. Protocol 1 used the original merge. Protocol 2 adds the
              R5.1 sibling-context rule, pre-registered after protocol 1 was
              reported and before its own re-run. Both are shown; protocol 1 is
              not replaced.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                suiteB.expectation_passed === suiteB.expectation_total
                  ? "ok"
                  : "danger"
              }
            >
              P1 {suiteB.expectation_passed}/{suiteB.expectation_total} met
            </Badge>
            <Badge
              variant={
                suiteBR51.expectation_passed === suiteBR51.expectation_total
                  ? "ok"
                  : "danger"
              }
            >
              P2 {suiteBR51.expectation_passed}/{suiteBR51.expectation_total} met
            </Badge>
            <Badge variant="outline">
              {suiteB.runs + suiteBR51.runs} suite B audits
            </Badge>
          </div>
        </div>

        {hasProtocolComparison ? (
          <>
            <SuiteBComparison p1={suiteB.models} p2={suiteBR51.models} />

            <div
              role="note"
              className="mt-3 rounded-lg border border-warn/35 bg-warn/[0.045] p-3"
            >
              <p className="flex items-center gap-2 text-[12px] font-semibold text-warn">
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                Protocol 2 is a refinement, not a clean first pass.
              </p>
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink">
                The sibling rule was designed after protocol 1&apos;s results and
                pre-registered before its own re-run. It is a failure-to-reject
                rule, not an equivalence test. It collapsed 8–10 findings to 1–3
                per audit but did not always reach exactly one. Models 11 and 14
                keep the same disclosed misses, and the clean controls stay at
                zero.
              </p>
            </div>

            <div className="mt-5">
              <h3 className="text-[13px] font-semibold">
                Protocol 2 detail (R5.1 sibling merge)
              </h3>
              <SuiteBTable rows={suiteBR51.models} />
              <SuiteBMisses rows={suiteBR51.models} />
            </div>

            <details className="panel mt-3 overflow-hidden">
              <summary className="cursor-pointer border-b border-line/60 px-4 py-2 font-mono text-[10px] text-muted hover:text-accent">
                Protocol 1 detail — kept ids, misses, Fairlearn, runtime
              </summary>
              <div className="px-4 py-3">
                <SuiteBTable rows={suiteB.models} />
                <SuiteBMisses rows={suiteB.models} />
              </div>
            </details>
          </>
        ) : suiteB.models.length > 0 ? (
          <>
            <p className="mt-4 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
              No protocol 2 result file was found. Protocol 1 is shown alone
              rather than padded with a placeholder number.
            </p>
            <SuiteBTable rows={suiteB.models} />
            <SuiteBMisses rows={suiteB.models} />
          </>
        ) : suiteBR51.models.length > 0 ? (
          <>
            <p className="mt-4 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
              No protocol 1 result file was found. Protocol 2 is shown alone.
            </p>
            <SuiteBTable rows={suiteBR51.models} />
            <SuiteBMisses rows={suiteBR51.models} />
          </>
        ) : (
          <p className="mt-4 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
            No suite B result file was found. The section is left empty rather
            than padded with a placeholder number.
          </p>
        )}

        <div className="mt-3">
          <SourceStrip sources={[...suiteB.sources, ...suiteBR51.sources]} />
        </div>

        {suiteBR51.markdown ? (
          <details className="panel mt-3 overflow-hidden">
            <summary className="cursor-pointer border-b border-line/60 px-4 py-2 font-mono text-[10px] text-muted hover:text-accent">
              suite_b_r51.md — the protocol 2 report and limitations
            </summary>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-[10.5px] leading-relaxed text-muted">
              {suiteBR51.markdown}
            </pre>
          </details>
        ) : (
          <p className="mt-3 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
            The protocol 2 notes file is missing, so no limitations summary is
            shown for it.
          </p>
        )}

        {suiteB.markdown ? (
          <details className="panel mt-3 overflow-hidden">
            <summary className="cursor-pointer border-b border-line/60 px-4 py-2 font-mono text-[10px] text-muted hover:text-accent">
              suite_b.md — the protocol 1 report and limitations
            </summary>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-[10.5px] leading-relaxed text-muted">
              {suiteB.markdown}
            </pre>
          </details>
        ) : (
          <p className="mt-3 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
            The protocol 1 notes file is missing, so no limitations summary is
            shown for it.
          </p>
        )}
      </section>

      <section className="mt-10" aria-labelledby="real-heading">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line/70 pb-3">
          <div>
            <p className="eyebrow">real datasets</p>
            <h2 id="real-heading" className="mt-1 flex items-center gap-2 text-xl font-semibold tracking-[-0.02em]">
              <Scale className="h-4 w-4 text-accent" aria-hidden="true" />
              Real models next to Fairlearn
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-muted">
              These are not the seven sandbox models. The probe population is the
              synthetic FairLens generator mapped into the dataset's columns, not
              the dataset's own population. Only probes the adapter declares are
              run.
            </p>
          </div>
          <Badge variant="outline">
            <BarChart3 className="mr-1 h-3 w-3" aria-hidden="true" />
            {real.models.length} evaluated targets
          </Badge>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {real.models.map((model) => (
            <RealModelCard key={model.model} model={model} />
          ))}
        </div>
        {real.models.length === 0 && (
          <p className="mt-4 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
            No real-model result file was found. Nothing is inferred to fill the
            gap.
          </p>
        )}
        <div className="mt-3">
          <SourceStrip sources={real.sources} />
        </div>
      </section>

      <section className="mt-10" aria-labelledby="notes-heading">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line/70 pb-3">
          <div>
            <p className="eyebrow">evaluation notes</p>
            <h2 id="notes-heading" className="mt-1 flex items-center gap-2 text-xl font-semibold tracking-[-0.02em]">
              <FileText className="h-4 w-4 text-accent" aria-hidden="true" />
              The full protocol and limitations
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-muted">
              Served verbatim from <span className="font-mono">real_models.md</span>{" "}
              so the caveats travel with the numbers.
            </p>
          </div>
        </div>
        {real.markdown ? (
          <details className="panel mt-3 overflow-hidden" open>
            <summary className="cursor-pointer border-b border-line/60 px-4 py-2 font-mono text-[10px] text-muted hover:text-accent">
              real_models.md — verbatim
            </summary>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-[10.5px] leading-relaxed text-muted">
              {real.markdown}
            </pre>
          </details>
        ) : (
          <p className="mt-4 rounded-lg border border-dashed border-line/70 px-3 py-4 text-[11px] text-muted">
            The evaluation notes file is missing, so no summary is shown.
          </p>
        )}
      </section>

      <p className="mt-10 flex items-center gap-1.5 text-[10.5px] text-muted/60">
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
        Raw files live under <span className="font-mono">eval/results/</span>. The
        API recomputes these aggregates on every request, so a stale UI cannot
        outlive the files.
      </p>
    </div>
  );
}

function EvidenceLoading() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-5 pb-24 pt-8">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-3 h-9 w-80 max-w-full" />
      <Skeleton className="mt-3 h-3 w-[34rem] max-w-full" />
      <div className="mt-8 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <CardSkeleton key={item} lines={1} />
        ))}
      </div>
      <div className="mt-4 space-y-2">
        {[0, 1, 2, 3, 4].map((item) => (
          <Skeleton key={item} className="h-10 w-full opacity-80" />
        ))}
      </div>
      <LoadingLine className="mt-4">reading the committed result files…</LoadingLine>
    </div>
  );
}
