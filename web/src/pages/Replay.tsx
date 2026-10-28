import * as React from "react";
import { useParams } from "react-router-dom";

import type { AuditRecord } from "@/api-types";
import { ArenaView } from "@/components/arena/ArenaView";
import { ReplayControls } from "@/components/arena/ReplayControls";
import { CardSkeleton, LoadingLine, Skeleton } from "@/components/ui/skeleton";
import { useArenaMeta } from "@/hooks/useArenaMeta";
import { useReplayPlayback } from "@/hooks/useReplayPlayback";
import { ApiError, api } from "@/lib/api";
import type { ReplayFile } from "@/api-types";

export function Replay() {
  const { replayId } = useParams();
  const { meta, metaError, targets, retryMeta } = useArenaMeta();

  const [replay, setReplay] = React.useState<ReplayFile | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [attempt, setAttempt] = React.useState(0);
  const [record, setRecord] = React.useState<AuditRecord | null>(null);
  const startedAt = React.useMemo(() => Date.now(), [replayId]);

  React.useEffect(() => {
    if (!replayId) {
      setError("missing replay id");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    api
      .getReplay(replayId)
      .then((value) => {
        if (!active) return;
        setReplay(value);
        setRecord(value.audit);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(
          cause instanceof ApiError ? cause.detail : "could not load the recording",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [replayId, attempt]);

  const playback = useReplayPlayback(replay);

  if (loading) {
    return <ReplayLoading />;
  }

  if (error || !replay) {
    return (
      <div className="mx-auto w-full max-w-[900px] px-5 py-20">
        <p className="eyebrow">recorded replay</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-[-0.02em]">
          This recording could not be loaded
        </h1>
        <div
          role="alert"
          className="mt-4 rounded-lg border border-danger/30 bg-danger/[0.04] p-4"
        >
          <p className="text-[12px] text-danger">
            {error ?? "replay not found"}
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted">
            replay id: {replayId ?? "—"}
          </p>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              setAttempt((value) => value + 1);
            }}
            className="rounded-md border border-line px-3 py-1.5 font-mono text-[10px] text-muted hover:border-accent/45 hover:text-accent"
          >
            Retry
          </button>
          <a
            href="/"
            className="rounded-md border border-line px-3 py-1.5 font-mono text-[10px] text-muted hover:border-accent/45 hover:text-accent"
          >
            model library
          </a>
        </div>
      </div>
    );
  }

  return (
    <ArenaView
      mode="replay"
      auditId={replay.audit.id}
      stream={playback}
      record={record}
      meta={meta}
      metaError={metaError}
      onRetryMeta={retryMeta}
      targets={targets}
      startedAt={startedAt}
      elapsedMs={playback.positionMs}
      replay={{
        id: replay.id,
        label: replay.label,
        sourceAuditId: replay.source_audit_id,
        recordedAt: replay.recorded_at,
      }}
      onDecided={setRecord}
      playbackBar={
        <ReplayControls
          playing={playback.playing}
          progress={playback.progress}
          positionMs={playback.positionMs}
          durationMs={playback.durationMs}
          speed={playback.speed}
          onToggle={playback.toggle}
          onRestart={playback.restart}
          onSeek={playback.seek}
          onSpeed={playback.setSpeed}
          onSkip={playback.skipToEnd}
        />
      }
    />
  );
}

function ReplayLoading() {
  return (
    <div className="mx-auto w-full max-w-[1500px] px-5 pb-20 pt-7">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-4 h-8 w-72 max-w-full" />
      <Skeleton className="mt-2 h-3 w-96 max-w-full" />
      <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,1fr)]">
        <CardSkeleton lines={6} className="min-h-[288px]" />
        <div className="space-y-4">
          <CardSkeleton lines={4} />
          <CardSkeleton lines={3} />
        </div>
      </div>
      <LoadingLine className="mt-4">loading the recording…</LoadingLine>
    </div>
  );
}
