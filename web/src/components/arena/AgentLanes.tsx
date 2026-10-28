import { FileText, Radar, ShieldQuestion, Sigma } from "lucide-react";

import type { AgentEvent } from "@/api-types";
import type { StreamStatus } from "@/hooks/useAuditStream";
import { laneForAgent, laneStates } from "@/lib/arena";
import { cn } from "@/lib/utils";

const LANE_META = {
  prober: {
    label: "Prober",
    blurb: "sends twin applicants and watches decisions",
    icon: Radar,
  },
  statistician: {
    label: "Statistician",
    blurb: "estimates the net flip rate and its interval",
    icon: Sigma,
  },
  skeptic: {
    label: "Skeptic",
    blurb: "tries to reject every candidate finding",
    icon: ShieldQuestion,
  },
  reporter: {
    label: "Reporter",
    blurb: "turns what survived into plain-language impact",
    icon: FileText,
  },
} as const;

export function AgentLanes({
  events,
  status,
}: {
  events: AgentEvent[];
  status: StreamStatus;
}) {
  const lanes = laneStates(events);
  const latestLane =
    events.length > 0 ? laneForAgent(events[events.length - 1].agent) : null;
  const live = status === "open" || status === "connecting" || status === "reconnecting";

  return (
    <section className="panel p-4" aria-label="Agent lanes">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="eyebrow">agent lanes</p>
          <h2 className="mt-1 text-[15px] font-semibold">Who is doing what</h2>
        </div>
        <span
          className={cn(
            "flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.16em]",
            live ? "text-accent" : "text-muted",
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              live ? "bg-accent animate-pulse-line" : "bg-muted",
            )}
            aria-hidden="true"
          />
          {status}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {lanes.map((lane) => {
          const meta = LANE_META[lane.id];
          const Icon = meta.icon;
          const active = latestLane === lane.id && live;
          return (
            <div
              key={lane.id}
              title={meta.blurb}
              aria-current={active ? "step" : undefined}
              className={cn(
                "rounded-lg border p-2.5 transition-colors",
                active
                  ? "border-accent/45 bg-accent/[0.055]"
                  : "border-line/60 bg-canvas/35",
              )}
            >
              <div className="flex items-center gap-1.5">
                <Icon
                  className={cn(
                    "h-3.5 w-3.5",
                    active ? "text-accent" : "text-muted/70",
                  )}
                  aria-hidden="true"
                />
                <span
                  className={cn(
                    "text-[11px] font-medium",
                    active ? "text-ink" : "text-muted",
                  )}
                >
                  {meta.label}
                </span>
                <span className="ml-auto font-mono text-[9px] text-muted/60">
                  {lane.count}
                </span>
              </div>
              <p className="mt-1 line-clamp-3 font-mono text-[9.5px] leading-relaxed text-muted/85">
                {lane.latest?.message ?? "waiting for its first action…"}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
