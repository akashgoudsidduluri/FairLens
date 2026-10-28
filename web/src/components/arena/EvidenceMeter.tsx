import { Info, TrendingDown, TrendingUp } from "lucide-react";
import * as React from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ProbeEvent } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useProbeArchive } from "@/hooks/useProbeArchive";
import {
  compactNumber,
  countNumber,
  evidenceGroups,
  evidenceSeries,
  probeSummary,
  signedPercent,
} from "@/lib/arena";
import { probeLabel } from "@/lib/stream";
import { cn } from "@/lib/utils";

export interface EvidenceMeterProps {
  events: ProbeEvent[];
  materiality: number;
  ciLevel: number;
  bootstrapIterations: number;
}

function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "default" | "ok" | "danger";
}) {
  return (
    <div className="rounded-lg border border-line/60 bg-canvas/40 px-2.5 py-2">
      <p className="flex items-center gap-1 text-[9px] uppercase tracking-[0.13em] text-muted">
        {label}
        <UiTooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`${label}: ${hint}`}
              className="text-muted/60 transition-colors hover:text-accent"
            >
              <Info className="h-2.5 w-2.5" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>{hint}</TooltipContent>
        </UiTooltip>
      </p>
      <p
        className={cn(
          "mt-0.5 font-mono text-[12px]",
          tone === "ok" && "text-ok",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </p>
    </div>
  );
}

export function EvidenceMeter({
  events,
  materiality,
  ciLevel,
  bootstrapIterations,
}: EvidenceMeterProps) {
  const [pinned, setPinned] = React.useState<string | null>(null);
  const archive = useProbeArchive(events, "live");
  const summaries = React.useMemo(
    () =>
      archive.order
        .map((probeId) => archive.byId[probeId])
        .filter((points) => points.length > 0)
        .map((points) => probeSummary(points[points.length - 1])),
    [archive],
  );
  const groups = React.useMemo(() => evidenceGroups(summaries), [summaries]);
  const latestGroupKey = groups.length > 0 ? groups[groups.length - 1].key : null;

  const activeGroupKey = pinned ?? latestGroupKey;
  const activeGroup = groups.find((group) => group.key === activeGroupKey) ?? null;
  const activeId = activeGroup?.latest.probeId ?? null;
  const active = React.useMemo(() => {
    if (!activeId) return null;
    const points = archive.byId[activeId];
    return points && points.length > 0 ? points[points.length - 1] : null;
  }, [archive, activeId]);

  const series = React.useMemo(
    () => (activeId ? evidenceSeries(archive.byId[activeId] ?? []) : []),
    [archive, activeId],
  );

  if (!active || !activeId || !activeGroup) {
    return (
      <section className="panel p-4" aria-label="Live evidence meter">
        <p className="eyebrow">live evidence</p>
        <h2 className="mt-1 text-[15px] font-semibold">Net flip rate</h2>
        <div className="mt-4 flex h-[140px] items-center justify-center rounded-lg border border-dashed border-line/80">
          <p className="font-mono text-[10.5px] text-muted">
            waiting for pairs to estimate the rate…
          </p>
        </div>
        <p className="mt-2 text-[10.5px] leading-relaxed text-muted/75">
          The live band is a normal approximation. Final findings use the seeded
          bootstrap.
        </p>
      </section>
    );
  }

  const above = Math.abs(active.net_flip_rate_running) >= materiality;
  const maxAbs = Math.max(
    materiality * 3,
    0.06,
    ...series.flatMap((point) => [
      Math.abs(point.net / 100),
      Math.abs(point.band[0] / 100),
      Math.abs(point.band[1] / 100),
    ]),
  );
  const domain = Number(((Math.ceil(maxAbs * 10) / 10) * 100).toFixed(1));

  return (
    <section className="panel p-4" aria-label="Live evidence meter">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="eyebrow">live evidence</p>
          <h2 className="mt-1 text-[15px] font-semibold">Net flip rate</h2>
        </div>
        <Badge variant={above ? "danger" : "outline"}>
          {above ? "above materiality" : "below materiality"}
        </Badge>
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-2">
        <span
          className={cn(
            "font-mono text-3xl tracking-tight",
            active.net_flip_rate_running > 0
              ? "text-danger"
              : active.net_flip_rate_running < 0
                ? "text-ok"
                : "text-ink",
          )}
        >
          {signedPercent(active.net_flip_rate_running)}
        </span>
        <span className="text-[11px] text-muted">
          over {compactNumber(active.n_running)} pairs ·{" "}
          {activeGroup.key === "intersectional"
            ? "combined attributes"
            : probeLabel(active.changed_field)}
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-2 text-[10.5px] text-muted">
        <span className="rounded border border-line/70 bg-raised/40 px-1.5 py-0.5 font-mono">
          {Math.round(ciLevel * 100)}% CI [{signedPercent(active.ci_low_running)},{" "}
          {signedPercent(active.ci_high_running)}]
        </span>
        <UiTooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-muted/75 underline decoration-line decoration-dotted underline-offset-2 hover:text-ink"
            >
              <Info className="h-2.5 w-2.5" aria-hidden="true" />
              live interval
            </button>
          </TooltipTrigger>
          <TooltipContent>
            This band is the normal approximation from the event stream. It
            narrows as pairs arrive. The final finding interval is the seeded
            bootstrap with {bootstrapIterations.toLocaleString()} resamples.
          </TooltipContent>
        </UiTooltip>
      </div>

      {groups.length > 1 && (
        <div
          className="mt-2.5 flex flex-wrap items-center gap-1"
          role="group"
          aria-label="Evidence by attribute"
        >
          <span className="mr-1 font-mono text-[9px] uppercase tracking-[0.14em] text-muted/60">
            by attribute
          </span>
          {groups.map((group) => {
            const selected = group.key === activeGroupKey;
            const harmful = group.latest.net > 0;
            return (
              <button
                key={group.key}
                type="button"
                onClick={() => setPinned(group.key)}
                aria-pressed={selected}
                title={`${group.latest.probeId} · ${group.latest.n.toLocaleString()} pairs · ${group.count} probe${group.count === 1 ? "" : "s"} seen`}
                className={cn(
                  "rounded border px-1.5 py-0.5 font-mono text-[9.5px] transition-colors",
                  selected
                    ? "border-accent/60 bg-accent/10 text-accent"
                    : "border-line/70 bg-raised/30 text-muted hover:border-accent/35 hover:text-ink",
                )}
              >
                {group.key === "intersectional"
                  ? "combined attributes"
                  : probeLabel(group.latest.changedField)}{" "}
                <span
                  className={cn(
                    harmful && "text-danger/90",
                    !harmful && group.latest.net < 0 && "text-ok/90",
                  )}
                >
                  {signedPercent(group.latest.net)}
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-3 h-[150px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={series}
            margin={{ top: 6, right: 6, bottom: 0, left: -18 }}
          >
            <CartesianGrid stroke="#1E2A36" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="n"
              type="number"
              domain={[0, "dataMax"]}
              tick={{ fill: "#8A9AA9", fontSize: 9 }}
              tickLine={false}
              axisLine={{ stroke: "#1E2A36" }}
              tickFormatter={(value: number) => compactNumber(value)}
            />
            <YAxis
              domain={[-domain, domain]}
              tick={{ fill: "#8A9AA9", fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => `${Math.round(value)}%`}
            />
            <Tooltip
              contentStyle={{
                background: "#0b131b",
                border: "1px solid #1E2A36",
                borderRadius: 8,
                fontSize: 11,
              }}
              labelFormatter={(value) => `after ${Number(value)} pairs`}
              formatter={(value) => {
                if (Array.isArray(value)) {
                  return [
                    `${Number(value[0]).toFixed(2)}% to ${Number(value[1]).toFixed(2)}%`,
                    "live interval",
                  ];
                }
                return [`${Number(value).toFixed(2)}%`, "net flip rate"];
              }}
            />
            <ReferenceLine y={0} stroke="#334252" strokeDasharray="3 4" />
            <ReferenceLine
              y={materiality * 100}
              stroke="#FB7185"
              strokeDasharray="4 4"
              label={{
                value: `materiality ${(materiality * 100).toFixed(1)}%`,
                fill: "#FB7185",
                fontSize: 9,
                position: "insideTopRight",
              }}
            />
            <Area
              type="monotone"
              dataKey="band"
              stroke="none"
              fill="#5EEAD4"
              fillOpacity={0.16}
              isAnimationActive={false}
              name="live interval"
            />
            <Line
              type="monotone"
              dataKey="net"
              stroke="#5EEAD4"
              strokeWidth={1.8}
              dot={false}
              isAnimationActive={false}
              name="net flip rate"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2">
        <Metric
          label="lost approval"
          value={countNumber(active.b_running)}
          hint="Twin pairs where the original was approved and the twin was rejected. In the target-group direction this is one unit of harm."
          tone={active.b_running > 0 ? "danger" : "default"}
        />
        <Metric
          label="gained approval"
          value={countNumber(active.c_running)}
          hint="Twin pairs where the original was rejected and the twin was approved. This subtracts from the net rate."
          tone={active.c_running > 0 ? "ok" : "default"}
        />
        <Metric
          label="pairs"
          value={countNumber(active.n_running)}
          hint="Pairs observed in the current attribute probe. Running statistics restart for each attribute."
        />
      </div>
      <div className="mt-2 flex items-start gap-1.5 text-[10px] leading-relaxed text-muted/75">
        {active.net_flip_rate_running >= 0 ? (
          <TrendingUp className="mt-0.5 h-3 w-3 shrink-0 text-danger/70" aria-hidden="true" />
        ) : (
          <TrendingDown className="mt-0.5 h-3 w-3 shrink-0 text-ok/70" aria-hidden="true" />
        )}
        <span>
          Positive means the twin lost approval while the original kept it. The
          dashed line is the pre-registered materiality threshold (
          {(materiality * 100).toFixed(1)}%). The live band is a normal
          approximation; final findings use the seeded bootstrap.
        </span>
      </div>
    </section>
  );
}
