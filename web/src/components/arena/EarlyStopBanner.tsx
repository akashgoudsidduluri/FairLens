import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { EarlyStop } from "@/lib/arena";
import { probeLabel } from "@/lib/stream";

export function EarlyStopBanner({ stop }: { stop: EarlyStop }) {
  return (
    <div
      role="status"
      aria-label="Early stop"
      className="flex flex-col gap-2 rounded-xl border border-warn/35 bg-warn/[0.06] px-4 py-3 sm:flex-row sm:items-center"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
        <Badge variant="warn">sequential stop</Badge>
      </div>
      <div className="min-w-0 text-[12px] leading-relaxed text-ink/90">
        <span className="font-medium">
          Stopped early on {probeLabel(stop.attribute)}:
        </span>{" "}
        {stop.message}.
        {stop.requestedN > 0 && (
          <span className="ml-1 font-mono text-[10.5px] text-muted">
            {stop.n.toLocaleString()} / {stop.requestedN.toLocaleString()} pairs
            checked
          </span>
        )}
      </div>
      <span className="ml-auto shrink-0 font-mono text-[9px] uppercase tracking-[0.14em] text-muted/70">
        rule fixed before the audit
      </span>
    </div>
  );
}
