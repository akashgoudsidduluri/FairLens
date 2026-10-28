import { useParams } from "react-router-dom";

import { useAuditStream } from "@/hooks/useAuditStream";

export function Arena() {
  const { auditId } = useParams();
  const stream = useAuditStream(auditId);

  return (
    <section className="mx-auto w-full max-w-[1400px] px-5 py-10">
      <p className="eyebrow">probe arena</p>
      <h1 className="mt-2 font-mono text-xl">{auditId}</h1>
      <p className="mt-4 text-sm text-muted">
        stream: <span className="font-mono text-accent">{stream.status}</span> · pairs{" "}
        <span className="font-mono">{stream.probeEvents.length}</span> · last event{" "}
        <span className="font-mono">{stream.lastEventId}</span>
      </p>
    </section>
  );
}
