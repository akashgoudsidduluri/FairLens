import * as React from "react";

import type { ServiceMeta, TargetCard } from "@/api-types";
import { ApiError, api } from "@/lib/api";

/**
 * Thresholds and target capabilities shared by the live arena and the replay
 * player. Both read the same pre-registered values, so the evidence meter draws
 * the identical materiality line in either mode.
 */
export function useArenaMeta() {
  const [meta, setMeta] = React.useState<ServiceMeta | null>(null);
  const [metaError, setMetaError] = React.useState<string | null>(null);
  const [targets, setTargets] = React.useState<TargetCard[]>([]);

  const retryMeta = React.useCallback(() => {
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

  React.useEffect(retryMeta, [retryMeta]);

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

  return { meta, metaError, targets, retryMeta };
}
