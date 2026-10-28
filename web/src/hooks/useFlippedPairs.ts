import * as React from "react";

import type { ProbeEvent } from "@/api-types";
import { isFlip, pairKey } from "@/lib/arena";

/**
 * Flips are kept in a bounded tray independently of the rendered stream.
 * The stream buffer is capped for memory; the tray survives that cap so an
 * early flip does not disappear when thousands of matching pairs follow it.
 */
export function useFlippedPairs(
  events: ProbeEvent[],
  auditId: string,
  cap = 40,
): ProbeEvent[] {
  const [flips, setFlips] = React.useState<ProbeEvent[]>([]);
  const seen = React.useRef<Set<string>>(new Set());

  React.useEffect(() => {
    setFlips([]);
    seen.current = new Set();
  }, [auditId]);

  React.useEffect(() => {
    const additions: ProbeEvent[] = [];
    for (const event of events) {
      if (!isFlip(event)) continue;
      const key = pairKey(event);
      if (seen.current.has(key)) continue;
      seen.current.add(key);
      additions.push(event);
    }
    if (additions.length === 0) return;
    setFlips((previous) => additions.reverse().concat(previous).slice(0, cap));
  }, [events, cap]);

  return flips;
}
