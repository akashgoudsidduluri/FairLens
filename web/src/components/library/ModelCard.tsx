import { ArrowRight, Check, Info, Loader2, Lock, X } from "lucide-react";

import type { TargetCard } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { probeLabel } from "@/lib/stream";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<TargetCard["kind"], string> = {
  validation: "validation suite",
  real: "real model",
  llm: "large language model",
};

const KIND_VARIANT: Record<TargetCard["kind"], "accent" | "ok" | "warn"> = {
  validation: "accent",
  real: "ok",
  llm: "warn",
};

function AvailabilityBadge({ card }: { card: TargetCard }) {
  const status = card.availability.status;
  if (status === "unavailable") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Badge variant="danger" className="gap-1.5">
              <Lock className="h-3 w-3" aria-hidden="true" />
              unavailable
            </Badge>
          </span>
        </TooltipTrigger>
        <TooltipContent>{card.availability.reason}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <Badge variant={status === "available" ? "ok" : "accent"} className="gap-1.5">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "available" ? "bg-ok" : "bg-accent",
        )}
        aria-hidden="true"
      />
      {status === "available" ? "ready" : "configured"}
    </Badge>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[10px] uppercase tracking-[0.14em] text-muted">
        {label}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="rounded-full text-muted/70 transition-colors hover:text-accent"
              aria-label={`${label}: ${hint}`}
            >
              <Info className="h-3 w-3" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>{hint}</TooltipContent>
        </Tooltip>
      </p>
      <p className="mt-1 font-mono text-[12px] text-ink">{value}</p>
    </div>
  );
}

export interface ModelCardProps {
  card: TargetCard;
  starting?: boolean;
  onStart: (card: TargetCard) => void;
}

export function ModelCard({ card, starting = false, onStart }: ModelCardProps) {
  const unavailable = card.availability.status === "unavailable";
  const unsupported = Object.entries(card.unsupported_probes);

  return (
    <Card className="flex h-full flex-col transition-colors hover:border-accent/30">
      <CardHeader className="gap-2">
        <div className="flex items-center justify-between gap-2">
          <Badge variant={KIND_VARIANT[card.kind]}>{KIND_LABEL[card.kind]}</Badge>
          <AvailabilityBadge card={card} />
        </div>
        <CardTitle>{card.label}</CardTitle>
        <CardDescription className="line-clamp-3">{card.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        <div>
          <p className="eyebrow">can test</p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Supported probes">
            {card.supported_probes.map((probe) => (
              <li
                key={probe}
                className="inline-flex items-center gap-1 rounded-md border border-ok/25 bg-ok/[0.07] px-1.5 py-0.5 font-mono text-[10px] text-ok"
              >
                <Check className="h-3 w-3" aria-hidden="true" />
                {probeLabel(probe)}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="eyebrow text-muted/80">cannot test</p>
          {unsupported.length === 0 ? (
            <p className="mt-2 text-[12px] text-muted">
              Nothing is ruled out for this target.
            </p>
          ) : (
            <ul className="mt-2 space-y-1" aria-label="Unsupported probes">
              {unsupported.map(([probe, reason]) => (
                <li key={probe} className="flex items-start gap-1.5 text-[12px]">
                  <X
                    className="mt-0.5 h-3 w-3 shrink-0 text-danger/80"
                    aria-hidden="true"
                  />
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        className="text-left text-muted underline decoration-line decoration-dotted underline-offset-2 transition-colors hover:text-ink"
                      >
                        {probeLabel(probe)}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>{reason}</TooltipContent>
                  </Tooltip>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-auto grid grid-cols-2 gap-3 border-t border-line/70 pt-3">
          <Stat
            label="twin pairs"
            value={card.planned_pairs.toLocaleString()}
            hint="Planned counterfactual pairs per attribute. Each pair sends two applicants who differ in exactly one field."
          />
          <Stat
            label="probe cap"
            value={card.probe_cap ? card.probe_cap.toLocaleString() : "no cap"}
            hint="Hard ceiling on applicants sent to this target in one audit. The audit fails rather than exceed it."
          />
        </div>
      </CardContent>

      <CardFooter className="flex-col items-stretch gap-2">
        <Button
          onClick={() => onStart(card)}
          disabled={unavailable || starting}
          aria-describedby={`${card.id}-availability`}
          className="w-full"
        >
          {starting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          )}
          {starting ? "starting…" : "Start audit"}
        </Button>
        <p
          id={`${card.id}-availability`}
          className={cn(
            "min-h-[14px] text-[11px] leading-snug",
            unavailable ? "text-danger/80" : "text-muted/80",
          )}
        >
          {unavailable
            ? card.availability.reason
            : card.metric ?? "capabilities read from the target adapter"}
        </p>
      </CardFooter>
    </Card>
  );
}
