import * as React from "react";
import { useParams } from "react-router-dom";

import type { AuditRecord, ServiceMeta, TargetCard } from "@/api-types";
import { ArenaView } from "@/components/arena/ArenaView";
import { useAuditStream } from "@/hooks/useAuditStream";
import { ApiError, api } from "@/lib/api";

export function Arena() {
  const { auditId } = useParams();
  const stream = useAuditStream(auditId);
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

  return (
    <ArenaView
      mode="live"
      auditId={auditId ?? ""}
      stream={stream}
      record={record}
      meta={meta}
      metaError={metaError}
      onRetryMeta={loadMeta}
      targets={targets}
      startedAt={startedAt}
      onDecided={setRecord}
    />
  );
}
