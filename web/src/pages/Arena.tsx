import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Loader2, WifiOff } from "lucide-react";

import type { AuditRecord, ServiceMeta, TargetCard } from "@/api-types";
import { AgentLanes } from "@/components/arena/AgentLanes";
import { BudgetPanel } from "@/components/arena/BudgetPanel";
import { EarlyStopBanner } from "@/components/arena/EarlyStopBanner";
import { EvidenceMeter } from "@/components/arena/EvidenceMeter";
import { FlippedTray } from "@/components/arena/FlippedTray";
import { TwinStream } from "@/components/arena/TwinStream";
import { ReportPanel } from "@/components/report/ReportPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuditStream } from "@/hooks/useAuditStream";
import { useFlippedPairs } from "@/hooks/useFlippedPairs";
import { useProbeRate } from "@/hooks/useProbeRate";
import { ApiError, api } from "@/lib/api";
import { latestEarlyStop, targetLabel } from "@/lib/arena";
import { cn } from "@/lib/utils";

const STATUS_VARIANT = {
  connecting: "outline",
  open: "accent",
  reconnecting: "warn",
  done: "ok",
  error: "danger",
} as const;

export function Arena() {
  const { auditId } = useParams();
  const stream = useAuditStream(auditId);
  const flips = useFlippedPairs(stream.probeEvents, auditId ?? "");
  const rate = useProbeRate(stream.probeCount);
  const startedAt = React.useMemo(() => Date.now(), [auditId]);

  const [meta, setMeta] = React.useState<ServiceMeta | null>(null);
  const [metaError, setMetaError] = React.useState<string | null>(null);
  const [record, setRecord] = React.useState<AuditRecord | null>(null);
  const [targets, setTargets] = React.useState<TargetCard[]>([]);

  const loadMeta = React.useCallback(() => {
    setMetaError(null);
    api
      .meta()
      .then(setMeta)
      .catch((cause: unknown) =>
        setMetaError(
          cause instanceof ApiError ? cause.detail : "could not read thresholds",
        ),
      );
  }, []);

  React.useEffect(loadMeta, [loadMeta]);

  React.useEffect(() => {
    let active = true;
    api
      .getTargets()
      .then((catalog) => active && setTargets(catalog.targets))
      .catch(() => {
        /* The global cap from /meta is a safe fallback. */
      });
    return () => {
      active = false;
    };
  }, []);

  React.useEffect(() => {
    if (!auditId) return;
    let active = true;
    api
      .getAudit(auditId)
      .then((value) => active && setRecord(value))
      .catch(() => {
        /* The stream reports connection failures; the record is optional. */
      });
    return () => {
      active = false;
    };
  }, [auditId, stream.done]);

  const earlyStop = React.useMemo(
    () => latestEarlyStop(stream.agentEvents),
    [stream.agentEvents],
  );
  const latestProbe = stream.probeEvents[stream.probeEvents.length - 1];
  const label = targetLabel(record?.target, record?.model_id);
  const findings = record?.result?.findings?.length;
  const targetCard = targets.find((card) => card.target === record?.target);
  const probeCap =
    record?.probe_cap ?? targetCard?.probe_cap ?? meta?.probe_cap ?? 0;
  const plannedPairs = targetCard?.planned_pairs ?? meta?.n_pairs ?? 0;

  return (
    <div className="mx-auto w-full max-w-[1500px] px-5 pb-20 pt-7">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-[11px] text-muted transition-colors hover:text-accent"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        model library
      </Link>

      <header className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">probe arena · live</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-0.025em] sm:text-3xl">
            {label}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-muted">
            <span>{auditId}</span>
            <span aria-hidden="true">·</span>
            <span>seed {record?.seed ?? "—"}</span>
            <span aria-hidden="true">·</span>
            <span>
              {latestProbe
                ? `${latestProbe.phase.replaceAll("_", " ")} · ${latestProbe.changed_field.replaceAll("_", " ")}`
                : "waiting for probes"}
            </span>
            {record?.sequential && (
              <>
                <span aria-hidden="true">·</span>
                <span>sequential on</span>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">model {record?.model_id ?? "—"}</Badge>
          <Badge variant={STATUS_VARIANT[stream.status]}>{stream.status}</Badge>
        </div>
      </header>

      <div className="mt-4 space-y-3">
        {earlyStop && <EarlyStopBanner stop={earlyStop} />}

        {stream.status === "reconnecting" && (
          <div
            role="status"
            className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/[0.05] px-3 py-2 text-[11.5px] text-warn"
          >
            <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
            Connection lost — resuming from event #{stream.lastEventId}. No frame is
            replayed twice.
          </div>
        )}

        {stream.done && (
          <div
            role="status"
            className={cn(
              "flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-[11.5px]",
              stream.done.status === "completed"
                ? "border-ok/30 bg-ok/[0.055] text-ok"
                : "border-danger/30 bg-danger/[0.055] text-danger",
            )}
          >
            {stream.done.status === "completed" ? (
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {stream.done.status === "completed"
              ? `Audit complete${typeof findings === "number" ? ` · ${findings} finding${findings === 1 ? "" : "s"} in the report` : ""}.`
              : `Audit failed: ${stream.done.error ?? "unknown error"}`}
            <span className="ml-auto font-mono text-[10px] text-muted">
              last event #{stream.lastEventId}
            </span>
          </div>
        )}

        {stream.status === "error" && !stream.done && (
          <p role="alert" className="text-[11.5px] text-danger">
            {stream.error ?? "the event stream stopped"}
          </p>
        )}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,1fr)]">
        <div className="space-y-4">
          <TwinStream events={stream.probeEvents} />
          <FlippedTray flips={flips} />
        </div>

        <div className="space-y-4">
          {meta ? (
            <EvidenceMeter
              events={stream.probeEvents}
              materiality={meta.materiality}
              ciLevel={meta.ci_level}
              bootstrapIterations={meta.bootstrap_iterations}
            />
          ) : (
            <ThresholdFallback error={metaError} onRetry={loadMeta} />
          )}

          <AgentLanes events={stream.agentEvents} status={stream.status} />

          <BudgetPanel
            probeCount={stream.probeCount}
            probeCap={probeCap}
            nPairs={plannedPairs}
            rate={rate}
            status={stream.status}
            lastEventId={stream.lastEventId}
            reconnects={stream.reconnects}
            startedAt={startedAt}
            sequentialEnabled={meta?.sequential_enabled ?? false}
          />
        </div>
      </div>

      {record?.result && (
        <ReportPanel
          record={record}
          report={record.result}
          agentEvents={stream.agentEvents}
          onDecided={setRecord}
        />
      )}
    </div>
  );
}

function ThresholdFallback({
  error,
  onRetry,
}: {
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <section className="panel p-4" aria-label="Live evidence meter">
      <p className="eyebrow">live evidence</p>
      <h2 className="mt-1 text-[15px] font-semibold">Net flip rate</h2>
      {error ? (
        <div role="alert" className="mt-3 rounded-lg border border-danger/25 bg-danger/[0.04] p-3">
          <p className="text-[11.5px] text-danger">
            Pre-registered thresholds are unavailable, so the meter stays off
            rather than guessing a line.
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted">{error}</p>
          <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2 font-mono text-[10.5px] text-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden="true" />
          reading pre-registered thresholds…
        </div>
      )}
    </section>
  );
}
