import * as React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDown, Boxes, FlaskConical, Loader2, Radio, Sparkles } from "lucide-react";

import type { TargetCard, TargetCatalog } from "@/api-types";
import { Logo } from "@/components/Logo";
import { ConnectEndpoint } from "@/components/library/ConnectEndpoint";
import { ModelCard } from "@/components/library/ModelCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; catalog: TargetCatalog }
  | { status: "error"; detail: string };

export function Landing() {
  const navigate = useNavigate();
  const [state, setState] = React.useState<LoadState>({ status: "loading" });
  const [startingId, setStartingId] = React.useState<string | null>(null);
  const [startError, setStartError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setState({ status: "loading" });
    api
      .getTargets()
      .then((catalog) => setState({ status: "ready", catalog }))
      .catch((cause: unknown) =>
        setState({
          status: "error",
          detail:
            cause instanceof ApiError
              ? cause.detail
              : "could not reach the audit service on port 8020",
        }),
      );
  }, []);

  React.useEffect(load, [load]);

  const start = async (card: TargetCard) => {
    setStartingId(card.id);
    setStartError(null);
    try {
      const created = await api.startAudit({
        model_id: card.model_id,
        target: card.target,
        include_mitigation: false,
        include_narrative: true,
      });
      navigate(`/audit/${created.id}`);
    } catch (cause) {
      setStartError(
        cause instanceof ApiError ? cause.detail : "could not start the audit",
      );
      setStartingId(null);
    }
  };

  const catalog = state.status === "ready" ? state.catalog.targets : [];
  const validation = catalog.filter((card) => card.kind === "validation");
  const real = catalog.filter((card) => card.kind === "real");
  const llm = catalog.filter((card) => card.kind === "llm");

  return (
    <div className="mx-auto w-full max-w-[1400px] px-5 pb-24">
      <section className="relative overflow-hidden rounded-2xl border border-line/70 bg-panel/40 px-6 py-14 sm:px-12 sm:py-20">
        <div className="grid-lines pointer-events-none absolute inset-0 opacity-40" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative max-w-3xl">
          <div className="flex items-center gap-4">
            <Logo size={48} />
            <div>
              <Badge variant="accent" className="gap-1.5">
                <Radio className="h-3 w-3" aria-hidden="true" />
                probe arena
              </Badge>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
                black-box fairness audit · synthetic first
              </p>
            </div>
          </div>

          <h1 className="mt-8 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-[56px]">
            See what the model does when{" "}
            <span className="text-accent">only one thing changes.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
            FairLens sends twin applicants through a lender model — identical
            except for gender, name, or region — and shows every decision live.
            A flip is a decision that changed for the same person.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button
              size="lg"
              onClick={() =>
                document
                  .getElementById("model-library")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" })
              }
            >
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
              Pick a model
            </Button>
            <span className="text-[12px] text-muted">
              No data upload. Every probe is a counterfactual twin.
            </span>
          </div>

          <dl className="mt-10 grid max-w-xl grid-cols-3 gap-4 border-t border-line/60 pt-6">
            <HeroStat value="7" label="validation models" />
            <HeroStat value="2" label="real datasets" />
            <HeroStat value="1" label="LLM screener" />
          </dl>
        </div>
      </section>

      <section id="model-library" className="scroll-mt-24 pt-16">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">
              <Boxes className="mr-1 inline h-3 w-3" aria-hidden="true" />
              model library
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.02em]">
              Pick what to put under the lens
            </h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
              Capabilities are read from each target adapter, not guessed by the
              browser. If a probe is undefined for a target, it is listed under
              “cannot test” with the reason.
            </p>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted/70">
            {state.status === "ready"
              ? `${catalog.length} targets · service online`
              : state.status === "error"
                ? "service offline"
                : "loading targets…"}
          </span>
        </div>

        {startError && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-danger/30 bg-danger/[0.06] px-3 py-2 text-[12px] text-danger"
          >
            {startError}
          </p>
        )}

        {state.status === "loading" && <LibrarySkeleton />}

        {state.status === "error" && (
          <div className="mt-8 rounded-xl border border-danger/25 bg-danger/[0.04] p-6">
            <p className="text-sm text-danger">The audit service is not answering.</p>
            <p className="mt-1 font-mono text-[11px] text-muted">{state.detail}</p>
            <p className="mt-3 text-[12px] text-muted">
              Start it with{" "}
              <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[11px] text-ink">
                python -m api.serve
              </code>{" "}
              on port 8020, then retry.
            </p>
            <Button variant="secondary" size="sm" className="mt-4" onClick={load}>
              Retry
            </Button>
          </div>
        )}

        {state.status === "ready" && (
          <>
            <SectionHeading
              icon={<FlaskConical className="h-4 w-4" aria-hidden="true" />}
              title="Validation suite"
              tag="7 synthetic models"
              description="Known planted behaviour, frozen thresholds. Use these to see the arena work end to end."
            />
            <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {validation.map((card) => (
                <ModelCard
                  key={card.id}
                  card={card}
                  starting={startingId === card.id}
                  onStart={start}
                />
              ))}
            </div>

            <SectionHeading
              className="pt-14"
              icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
              title="Real models"
              tag="2 datasets"
              description="Trained on UCI credit default and Adult Income. Only probes the data can actually answer are offered."
            />
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {real.map((card) => (
                <ModelCard
                  key={card.id}
                  card={card}
                  starting={startingId === card.id}
                  onStart={start}
                />
              ))}
            </div>

            <SectionHeading
              className="pt-14"
              icon={<Radio className="h-4 w-4" aria-hidden="true" />}
              title="LLM screener"
              tag="availability is real"
              description="An Anthropic model screens each applicant from a prompt. The card reads its availability from the server's environment, so it cannot show a fake green light."
            />
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {llm.map((card) => (
                <ModelCard
                  key={card.id}
                  card={card}
                  starting={startingId === card.id}
                  onStart={start}
                />
              ))}
              <div className="panel flex flex-col justify-center gap-3 p-6">
                <p className="eyebrow">why this matters</p>
                <p className="text-[13px] leading-relaxed text-muted">
                  A screener with no model or API key cannot run. FairLens reports
                  that plainly instead of fabricating decisions or silently
                  skipping the audit.
                </p>
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted/70">
                  checked at page load · server side
                </p>
              </div>
            </div>
          </>
        )}
      </section>

      <section className="pt-16">
        <div className="mb-5">
          <p className="eyebrow">your own model</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.02em]">
            Bring a black box
          </h2>
        </div>
        <ConnectEndpoint onStarted={(id) => navigate(`/audit/${id}`)} />
      </section>
    </div>
  );
}

function HeroStat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dt className="font-mono text-2xl text-ink">{value}</dt>
      <dd className="mt-0.5 text-[11px] uppercase tracking-[0.14em] text-muted">
        {label}
      </dd>
    </div>
  );
}

function SectionHeading({
  icon,
  title,
  tag,
  description,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  tag: string;
  description: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-accent">{icon}</span>
        <h3 className="text-lg font-semibold tracking-[-0.01em]">{title}</h3>
        <Badge variant="outline">{tag}</Badge>
      </div>
      <p className="mt-1.5 max-w-3xl text-[12.5px] leading-relaxed text-muted">
        {description}
      </p>
    </div>
  );
}

function LibrarySkeleton() {
  return (
    <div className="mt-8 flex items-center gap-2 font-mono text-[11px] text-muted">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden="true" />
      reading target capabilities…
    </div>
  );
}
