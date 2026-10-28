import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Hash, Loader2, ShieldCheck, ShieldX, TriangleAlert } from "lucide-react";

import type { Certificate, VerifyResponse } from "@/api-types";
import { CertificateCard } from "@/components/report/CertificateCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton, LoadingLine } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

type VerifyState =
  | { status: "unchecked" }
  | { status: "checking" }
  | { status: "verified"; result: VerifyResponse }
  | { status: "broken"; result: VerifyResponse };

export function Certificates() {
  const [records, setRecords] = React.useState<Certificate[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [verify, setVerify] = React.useState<VerifyState>({ status: "unchecked" });
  const [confirmTamper, setConfirmTamper] = React.useState(false);
  const [tampering, setTampering] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    api
      .certificates()
      .then((payload) => setRecords(payload.records))
      .catch((cause: unknown) =>
        setLoadError(
          cause instanceof ApiError
            ? cause.detail
            : "could not read the certificate store",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  const runVerify = async () => {
    setVerify({ status: "checking" });
    setActionError(null);
    try {
      const result = await api.verifyCertificates();
      setVerify({
        status: result.verified ? "verified" : "broken",
        result,
      });
    } catch (cause) {
      setVerify({ status: "unchecked" });
      setActionError(
        cause instanceof ApiError ? cause.detail : "could not verify the chain",
      );
    }
  };

  const runTamper = async () => {
    if (!records || records.length === 0 || !confirmTamper) return;
    setTampering(true);
    setActionError(null);
    try {
      const response = await api.tamperCertificate(records.length - 1);
      setVerify({
        status: response.verification.verified ? "verified" : "broken",
        result: response.verification,
      });
      load();
    } catch (cause) {
      setActionError(
        cause instanceof ApiError ? cause.detail : "could not run the tamper demo",
      );
    } finally {
      setTampering(false);
      setConfirmTamper(false);
    }
  };

  const brokenIndex =
    verify.status === "broken" ? verify.result.first_broken : null;
  const count = records?.length ?? 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-5 pb-24 pt-7">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-[11px] text-muted transition-colors hover:text-accent"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        model library
      </Link>

      <header className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">trust layer</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-0.025em] sm:text-3xl">
            Certificate chain
          </h1>
          <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-muted">
            Each human decision appends one record whose hash covers the previous
            record. Verification recomputes the chain; it proves tamper-evidence,
            not authorship.
          </p>
        </div>
        <VerifyBadge state={verify} count={count} />
      </header>

      {(loadError || actionError) && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-danger/30 bg-danger/[0.06] px-3 py-2 text-[12px] text-danger"
        >
          {loadError ?? actionError}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={runVerify}
          disabled={verify.status === "checking" || count === 0}
        >
          {verify.status === "checking" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Verify chain
        </Button>
        <span className="text-[10.5px] text-muted">
          {count === 0
            ? "Nothing to verify until a decision is issued."
            : verify.status === "unchecked"
              ? "Not checked yet. Verification is a deliberate step."
              : verify.status === "checking"
                ? "Recomputing every hash…"
                : verify.result.verified
                  ? `${recordsLabel(verify.result.records)} recomputed without a break.`
                  : `First break at record #${verify.result.first_broken ?? "?"}.`}
        </span>
      </div>

      {records === null && !loadError && (
        <div className="mt-6">
          <LoadingLine>reading the certificate store…</LoadingLine>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <CardSkeleton lines={5} />
            <CardSkeleton lines={5} />
          </div>
        </div>
      )}

      {records && records.length === 0 && (
        <section className="panel mt-6 p-6" aria-label="Empty certificate chain">
          <div className="flex items-center gap-2 text-muted">
            <Hash className="h-4 w-4" aria-hidden="true" />
            <p className="text-[13px]">No certificates yet.</p>
          </div>
          <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
            Open a completed audit, enter an approver name, and issue a decision.
            The first record becomes the genesis record.
          </p>
        </section>
      )}

      {records && records.length > 0 && (
        <>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {records.map((certificate) => (
              <CertificateCard
                key={certificate.index}
                certificate={certificate}
                broken={brokenIndex === certificate.index}
              />
            ))}
          </div>

          <section
            className="panel mt-6 border-warn/25 p-4"
            aria-label="Tamper demonstration"
          >
            <div className="flex items-start gap-2">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
              <div>
                <h2 className="text-[13px] font-semibold">Tamper demo</h2>
                <p className="mt-1 text-[11px] leading-relaxed text-muted">
                  This deliberately corrupts the newest record in the local demo
                  database. Verify the chain afterwards to see the first broken
                  record highlighted. Do not run it before a presentation unless
                  you want the chain to stay broken.
                </p>
                <label className="mt-3 flex items-start gap-2 text-[11px] text-muted">
                  <input
                    type="checkbox"
                    checked={confirmTamper}
                    onChange={(event) => setConfirmTamper(event.target.checked)}
                    className="mt-0.5 h-3.5 w-3.5 accent-[#5EEAD4]"
                  />
                  I understand this writes a corrupt record to the demo store.
                </label>
                <Button
                  size="sm"
                  variant="danger"
                  className="mt-3"
                  onClick={runTamper}
                  disabled={!confirmTamper || tampering}
                >
                  {tampering ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <ShieldX className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  Tamper with newest record
                </Button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function recordsLabel(count: number): string {
  return `${count} ${count === 1 ? "record" : "records"}`;
}

function VerifyBadge({ state, count }: { state: VerifyState; count: number }) {
  if (state.status === "verified") {
    return (
      <Badge variant="ok" className="gap-1">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        chain verified · {recordsLabel(count)}
      </Badge>
    );
  }
  if (state.status === "broken") {
    return (
      <Badge variant="danger" className="gap-1">
        <ShieldX className="h-3 w-3" aria-hidden="true" />
        chain broken · {recordsLabel(count)}
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className={cn("gap-1", state.status === "checking" && "text-accent")}
    >
      <Hash className="h-3 w-3" aria-hidden="true" />
      {state.status === "checking" ? "checking" : "not checked"} ·{" "}
      {recordsLabel(count)}
    </Badge>
  );
}
