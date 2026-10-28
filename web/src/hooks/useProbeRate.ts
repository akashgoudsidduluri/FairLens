import * as React from "react";

/**
 * Pairs per second over a rolling window.
 *
 * Probe frames arrive in batches, so the rate is computed from samples of the
 * monotonic probe count rather than one timestamp per frame. When no pairs
 * arrive for a window the rate falls back to zero instead of freezing.
 */
export function useProbeRate(
  probeCount: number,
  { windowMs = 4000, tickMs = 500 }: { windowMs?: number; tickMs?: number } = {},
): number {
  const samples = React.useRef<Array<{ at: number; count: number }>>([
    { at: Date.now(), count: probeCount },
  ]);
  const latest = React.useRef(probeCount);
  const [rate, setRate] = React.useState(0);

  latest.current = probeCount;

  React.useEffect(() => {
    samples.current.push({ at: Date.now(), count: probeCount });
    if (samples.current.length > 240) samples.current = samples.current.slice(-240);
  }, [probeCount]);

  React.useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      samples.current = samples.current.filter(
        (sample) => now - sample.at <= windowMs,
      );
      if (samples.current.length === 0) {
        samples.current.push({ at: now, count: latest.current });
      }
      const first = samples.current[0];
      const last = samples.current[samples.current.length - 1];
      const seconds = (last.at - first.at) / 1000;
      const delta = last.count - first.count;
      setRate(seconds > 0 && delta >= 0 ? delta / seconds : 0);
    }, tickMs);
    return () => clearInterval(timer);
  }, [windowMs, tickMs]);

  return rate;
}
