import * as React from "react";
import { Gauge, Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { StreamStatus } from "@/hooks/useAuditStream";
import { countNumber } from "@/lib/arena";
import { cn } from "@/lib/utils";

function useElapsed(startedAt: number): string {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[9px] uppercase tracking-[0.13em] text-muted">
        {label}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`${label}: ${hint}`}
              className="text-muted/60 hover:text-accent"
            >
              <Info className="h-2.5 w-2.5" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>{hint}</TooltipContent>
        </Tooltip>
      </p>
      <p className="mt-0.5 font-mono text-[12px] text-ink">{value}</p>
    </div>
  );
}

export interface BudgetPanelProps {
  probeCount: number;
  probeCap: number;
  nPairs: number;
  rate: number;
  status: StreamStatus;
  lastEventId: number;
  reconnects: number;
  startedAt: number;
  sequentialEnabled: boolean;
}

export function BudgetPanel({
  probeCount,
  probeCap,
  nPairs,
  rate,
  status,
  lastEventId,
  reconnects,
  startedAt,
  sequentialEnabled,
}: BudgetPanelProps) {
  const used = probeCount * 2;
  const cap = probeCap > 0 ? probeCap : 0;
  const percent = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
  const elapsed = useElapsed(startedAt);

  return (
    <section className="panel p-4" aria-label="Probe budget">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-accent" aria-hidden="true" />
          <div>
            <p className="eyebrow">probe budget</p>
            <h2 className="mt-0.5 text-[15px] font-semibold">Spend and rate</h2>
          </div>
        </div>
        <Badge variant={status === "done" ? "ok" : status === "error" ? "danger" : "outline"}>
          {status}
        </Badge>
      </div>

      <div className="mt-3">
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-mono text-[13px] text-ink">
            {countNumber(used)}{" "}
            <span className="text-muted">/ {countNumber(cap)} applicants</span>
          </p>
          <span className="font-mono text-[10px] text-muted">{percent.toFixed(1)}%</span>
        </div>
        <div
          className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line/60"
          role="progressbar"
          aria-label="Probe budget used"
          aria-valuemin={0}
          aria-valuemax={cap}
          aria-valuenow={Math.min(used, cap)}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500",
              percent >= 90 ? "bg-danger" : "bg-accent",
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className="mt-1 text-[10px] leading-snug text-muted/75">
          Each twin pair sends two applicants. The cap is enforced server-side;
          the audit fails rather than exceed it.
        </p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-line/60 pt-3">
        <Stat
          label="pairs observed"
          value={countNumber(probeCount)}
          hint="Probe frames received. A pair is two applicants who differ in exactly one field."
        />
        <Stat
          label="rate"
          value={rate > 0 ? `${rate.toFixed(1)} pairs/s` : "—"}
          hint="Rolling four-second average. Frames arrive in batches, so the rate is smoothed rather than per-event."
        />
        <Stat
          label="planned / attribute"
          value={countNumber(nPairs)}
          hint="Pre-registered number of pairs per single attribute in config.yaml. This is not tuned after seeing results."
        />
        <Stat
          label="elapsed"
          value={elapsed}
          hint="Time since this arena opened, not since the audit was queued."
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line/60 pt-2.5 font-mono text-[9.5px] text-muted/70">
        <span>event #{lastEventId.toLocaleString()}</span>
        <span>
          sequential stopping:{" "}
          <span className={sequentialEnabled ? "text-accent" : "text-muted"}>
            {sequentialEnabled ? "pre-registered · on" : "off"}
          </span>
        </span>
        {reconnects > 0 && (
          <span className="text-warn">resumed {reconnects}×</span>
        )}
      </div>
    </section>
  );
}
