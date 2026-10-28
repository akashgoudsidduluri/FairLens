import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Inbox } from "lucide-react";

import type { ProbeEvent } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { pairKey } from "@/lib/arena";
import { probeLabel } from "@/lib/stream";
import { cn } from "@/lib/utils";

function stamp(approved: boolean) {
  return cn(
    "font-mono text-[10px] uppercase tracking-[0.12em]",
    approved ? "text-ok" : "text-danger",
  );
}

export function FlippedTray({ flips }: { flips: ProbeEvent[] }) {
  return (
    <section className="panel flex h-full flex-col p-4" aria-label="Flipped pairs">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="eyebrow text-danger/90">flipped tray</p>
          <h2 className="mt-1 text-[15px] font-semibold">Decisions that changed</h2>
        </div>
        <Badge variant={flips.length > 0 ? "danger" : "outline"}>
          {flips.length} kept
        </Badge>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-muted/80">
        The tray survives the on-screen pair cap. Newest flip first, capped at
        40.
      </p>

      {flips.length === 0 ? (
        <div className="mt-3 flex min-h-[100px] flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-line/80 text-center">
          <Inbox className="h-4 w-4 text-muted/60" aria-hidden="true" />
          <p className="mt-1 font-mono text-[10.5px] text-muted">
            no flips yet — {`they land here`}
          </p>
        </div>
      ) : (
        <ul className="mt-3 max-h-[300px] space-y-1.5 overflow-y-auto pr-1">
          <AnimatePresence initial={false}>
            {flips.map((event) => (
              <motion.li
                key={pairKey(event)}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded-lg border border-danger/25 bg-danger/[0.045] px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] text-ink">
                    #{event.pair_index + 1} · {probeLabel(event.changed_field)}
                  </span>
                  <span className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-muted/70">
                    {event.phase.replaceAll("_", " ")}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1.5">
                  <span className={stamp(event.original_approved)}>
                    {event.original_approved ? "approved" : "rejected"}
                  </span>
                  <ArrowRight className="h-3 w-3 text-muted" aria-hidden="true" />
                  <span className={stamp(event.twin_approved)}>
                    {event.twin_approved ? "approved" : "rejected"}
                  </span>
                  <span className="ml-auto font-mono text-[8.5px] text-muted/60">
                    {event.probe_id}
                  </span>
                </div>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}
