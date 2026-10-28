import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeftRight, Equal, Zap } from "lucide-react";

import type { ProbeEvent } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { fieldLabel, probeLabel } from "@/lib/stream";
import { isFlip, pairKey } from "@/lib/arena";
import { cn } from "@/lib/utils";

const MAX_VISIBLE_PAIRS = 5;
const FADE_AFTER_MS = 1400;

const SUMMARY_FIELDS = [
  { key: "income", label: "annual income" },
  { key: "gender", label: "gender" },
  { key: "age_band", label: "age band" },
  { key: "urban_rural", label: "location" },
  { key: "pincode_group", label: "region group" },
  { key: "name_group", label: "name group" },
] as const;

const PHASE_LABEL: Record<ProbeEvent["phase"], string> = {
  single_attribute: "single attribute",
  intersectional: "combined cells",
  matched_retest: "matched retest",
};

function displayValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (key === "income" && typeof value === "number") {
    return `₹${value.toLocaleString("en-IN")}`;
  }
  return String(value).replaceAll("_", " ");
}

function DecisionStamp({ approved }: { approved: boolean }) {
  return (
    <span
      className={cn(
        "rotate-[-1.5deg] rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em]",
        approved
          ? "border-ok/45 bg-ok/[0.07] text-ok"
          : "border-danger/45 bg-danger/[0.07] text-danger",
      )}
    >
      {approved ? "approved" : "rejected"}
    </span>
  );
}

function ApplicantCard({
  side,
  applicant,
  approved,
  changedField,
}: {
  side: "original" | "twin";
  applicant: Record<string, unknown>;
  approved: boolean;
  changedField: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-2.5",
        side === "twin" ? "border-line bg-panel/70" : "border-line/70 bg-canvas/50",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
          {side === "original" ? "a · original" : "b · twin"}
        </span>
        <DecisionStamp approved={approved} />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1">
        {SUMMARY_FIELDS.map((field) => {
          const changed = changedField === field.key;
          return (
            <div
              key={field.key}
              className={cn(
                "rounded px-1 py-0.5",
                changed && "bg-accent/10 ring-1 ring-inset ring-accent/35",
              )}
            >
              <dt
                className={cn(
                  "text-[8.5px] uppercase tracking-[0.12em]",
                  changed ? "text-accent" : "text-muted/70",
                )}
              >
                {field.label}
                {changed ? " · changed" : ""}
              </dt>
              <dd
                className={cn(
                  "truncate font-mono text-[11px]",
                  changed ? "text-accent" : "text-ink",
                )}
                title={displayValue(field.key, applicant[field.key])}
              >
                {displayValue(field.key, applicant[field.key])}
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="mt-1.5 truncate font-mono text-[9px] text-muted/60">
        applicant #{String(applicant.id ?? "—")}
      </p>
    </div>
  );
}

function PairCard({ event }: { event: ProbeEvent }) {
  const flip = isFlip(event);
  const [settled, setSettled] = React.useState(false);

  React.useEffect(() => {
    if (flip) return;
    const timer = setTimeout(() => setSettled(true), FADE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [flip]);

  return (
    <motion.article
      layout
      data-testid="twin-pair"
      data-flip={flip ? "true" : "false"}
      initial={{ opacity: 0, y: -16, scale: 0.985 }}
      animate={{
        opacity: !flip && settled ? 0.3 : 1,
        y: 0,
        scale: 1,
      }}
      exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.16 } }}
      transition={{ type: "spring", stiffness: 260, damping: 26 }}
      className={cn(
        "rounded-xl border p-3",
        flip
          ? "border-danger/40 bg-danger/[0.035] shadow-[0_0_24px_rgba(251,113,133,0.08)] animate-flip"
          : "border-line/70 bg-raised/20",
      )}
    >
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] text-muted">
          pair #{event.pair_index + 1}
        </span>
        <Badge variant="outline">{PHASE_LABEL[event.phase]}</Badge>
        <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted">
          <ArrowLeftRight className="h-3 w-3" aria-hidden="true" />
          changed: {probeLabel(event.changed_field)}
        </span>
        <span className="ml-auto">
          {flip ? (
            <Badge variant="danger" className="gap-1">
              <Zap className="h-3 w-3" aria-hidden="true" />
              flipped
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1">
              <Equal className="h-3 w-3" aria-hidden="true" />
              {settled ? "same decision · faded" : "same decision"}
            </Badge>
          )}
        </span>
      </header>

      <div className="grid gap-2 sm:grid-cols-2">
        <ApplicantCard
          side="original"
          applicant={event.original}
          approved={event.original_approved}
          changedField={event.changed_field}
        />
        <ApplicantCard
          side="twin"
          applicant={event.twin}
          approved={event.twin_approved}
          changedField={event.changed_field}
        />
      </div>

      {flip && (
        <p className="mt-2 text-[10.5px] leading-snug text-danger/85">
          Same applicant, only {fieldLabel(event.changed_field)} changed — the
          decision flipped.
        </p>
      )}
    </motion.article>
  );
}

export function TwinStream({ events }: { events: ProbeEvent[] }) {
  const visible = React.useMemo(
    () => events.slice(-MAX_VISIBLE_PAIRS).reverse(),
    [events],
  );

  return (
    <section className="panel flex h-full flex-col p-4" aria-label="Twin stream">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">twin stream</p>
          <h2 className="mt-1 text-[15px] font-semibold">
            Same person, one field changed
          </h2>
        </div>
        <Badge variant="outline">{MAX_VISIBLE_PAIRS} on screen max</Badge>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-muted/80">
        A flip flashes red and drops into the flipped tray. Matching pairs fade
        after a moment so the next pair is easy to read.
      </p>

      <div className="mt-3 min-h-[240px] flex-1 space-y-3">
        <AnimatePresence initial={false}>
          {visible.map((event) => (
            <PairCard key={pairKey(event)} event={event} />
          ))}
        </AnimatePresence>
        {visible.length === 0 && (
          <div className="flex h-full min-h-[220px] flex-col items-center justify-center rounded-lg border border-dashed border-line/80 text-center">
            <p className="font-mono text-[11px] text-muted">
              waiting for the first twin pair…
            </p>
            <p className="mt-1 max-w-xs text-[11px] text-muted/70">
              Pairs arrive in batches over the event stream and slide in here.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
