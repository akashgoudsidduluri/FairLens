import * as React from "react";

import type { ProbeEvent } from "@/api-types";
import { appendArchivedPoint, pairKey } from "@/lib/arena";

export interface ProbeArchive {
  /** Probe ids in the order they first appeared. */
  order: string[];
  byId: Record<string, ProbeEvent[]>;
}

const EMPTY: ProbeArchive = { order: [], byId: {} };

/**
 * Keeps a downsampled history for every attribute probe.
 *
 * The stream buffer is capped so the arena stays responsive, which means the
 * events for an earlier attribute eventually scroll out. The evidence strip
 * must not forget a material gender finding just because a later probe is
 * running, so this archive absorbs events as they arrive and keeps at most a
 * few hundred points per probe.
 */
export function useProbeArchive(
  events: ProbeEvent[],
  auditId: string,
): ProbeArchive {
  const [archive, setArchive] = React.useState<ProbeArchive>(EMPTY);
  const seen = React.useRef<Set<string>>(new Set());

  React.useEffect(() => {
    setArchive(EMPTY);
    seen.current = new Set();
  }, [auditId]);

  React.useEffect(() => {
    const fresh = events.filter((event) => !seen.current.has(pairKey(event)));
    if (fresh.length === 0) return;
    for (const event of fresh) seen.current.add(pairKey(event));

    setArchive((previous) => {
      const order = [...previous.order];
      const byId = { ...previous.byId };
      for (const event of fresh) {
        const existing = byId[event.probe_id];
        if (!existing) order.push(event.probe_id);
        byId[event.probe_id] = appendArchivedPoint(existing ?? [], event);
      }
      return { order, byId };
    });
  }, [events]);

  return archive;
}
