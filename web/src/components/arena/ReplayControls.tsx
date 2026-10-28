import { Gauge, Pause, Play, RotateCcw, SkipForward } from "lucide-react";

import { Button } from "@/components/ui/button";
import { REPLAY_SPEEDS } from "@/hooks/useReplayPlayback";
import { cn } from "@/lib/utils";

function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export interface ReplayControlsProps {
  playing: boolean;
  progress: number;
  positionMs: number;
  durationMs: number;
  speed: number;
  onToggle: () => void;
  onRestart: () => void;
  onSeek: (fraction: number) => void;
  onSpeed: (speed: number) => void;
  onSkip: () => void;
}

export function ReplayControls({
  playing,
  progress,
  positionMs,
  durationMs,
  speed,
  onToggle,
  onRestart,
  onSeek,
  onSpeed,
  onSkip,
}: ReplayControlsProps) {
  return (
    <section
      className="panel flex flex-wrap items-center gap-3 px-3 py-2.5"
      aria-label="Replay playback"
    >
      <Button
        size="sm"
        onClick={onToggle}
        aria-label={playing ? "Pause replay" : "Play replay"}
      >
        {playing ? (
          <Pause className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {playing ? "Pause" : "Play"}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        onClick={onRestart}
        aria-label="Restart replay from the beginning"
      >
        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
        Restart
      </Button>

      <div className="flex min-w-[180px] flex-1 items-center gap-2">
        <span className="font-mono text-[10px] tabular-nums text-muted">
          {clock(positionMs)}
        </span>
        <input
          type="range"
          min={0}
          max={1000}
          step={1}
          value={Math.round(progress * 1000)}
          onChange={(event) => onSeek(Number(event.target.value) / 1000)}
          aria-label="Replay position"
          aria-valuetext={`${clock(positionMs)} of ${clock(durationMs)}`}
          className="replay-range h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line accent-accent"
        />
        <span className="font-mono text-[10px] tabular-nums text-muted">
          {clock(durationMs)}
        </span>
      </div>

      <div className="flex items-center gap-1" role="group" aria-label="Playback speed">
        <Gauge className="mr-1 h-3 w-3 text-muted" aria-hidden="true" />
        {REPLAY_SPEEDS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onSpeed(value)}
            aria-pressed={speed === value}
            className={cn(
              "rounded border px-1.5 py-0.5 font-mono text-[9.5px] transition-colors",
              speed === value
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-line text-muted hover:border-accent/40 hover:text-accent",
            )}
          >
            {value}×
          </button>
        ))}
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={onSkip}
        aria-label="Skip replay to the report"
      >
        <SkipForward className="h-3.5 w-3.5" aria-hidden="true" />
        Skip to report
      </Button>
    </section>
  );
}
