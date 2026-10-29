import { CheckCircle2, Link2, XCircle } from "lucide-react";

import type { Certificate } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

function payloadString(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

export function CertificateCard({
  certificate,
  broken = false,
}: {
  certificate: Certificate;
  broken?: boolean;
}) {
  const approver = payloadString(certificate.payload, "approver") ?? "unknown";
  const decision = payloadString(certificate.payload, "decision") ?? "unknown";
  const approved = decision === "approve";

  return (
    <article
      className={cn(
        "rounded-xl border bg-panel/70 p-4",
        broken ? "border-danger/60" : "border-line/70",
      )}
      aria-label={`Audit Record ${certificate.index}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link2 className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
          <p className="font-mono text-[11px] text-ink">
            record #{certificate.index}
          </p>
          {certificate.index === 0 && (
            <Badge variant="outline">genesis</Badge>
          )}
        </div>
        <Badge variant={approved ? "ok" : "danger"}>
          {approved ? (
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          ) : (
            <XCircle className="h-3 w-3" aria-hidden="true" />
          )}
          {decision}
        </Badge>
      </div>

      <p className="mt-2 text-[12px] text-ink">{approver}</p>
      <p className="font-mono text-[10px] text-muted">{certificate.created_at}</p>

      <dl className="mt-3 space-y-1.5">
        <div>
          <dt className="font-mono text-[9px] uppercase tracking-[0.13em] text-muted/60">
            record hash
          </dt>
          <dd className="hash break-all">{certificate.record_hash}</dd>
        </div>
        <div>
          <dt className="font-mono text-[9px] uppercase tracking-[0.13em] text-muted/60">
            previous hash
          </dt>
          <dd className="hash break-all">{certificate.prev_hash}</dd>
        </div>
      </dl>
      {broken && (
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-danger">
          hash mismatch · first broken record
        </p>
      )}
    </article>
  );
}
