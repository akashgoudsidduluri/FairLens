import * as React from "react";
import { Link, Route, Routes } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import { ClipboardList, Hash } from "lucide-react";

import { Logo, Wordmark } from "@/components/Logo";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton, LoadingLine, Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";

// Recharts and the arena only load once a visitor leaves the library.
const Landing = React.lazy(() =>
  import("@/pages/Landing").then((module) => ({ default: module.Landing })),
);
const Arena = React.lazy(() =>
  import("@/pages/Arena").then((module) => ({ default: module.Arena })),
);
const Replay = React.lazy(() =>
  import("@/pages/Replay").then((module) => ({ default: module.Replay })),
);
const Certificates = React.lazy(() =>
  import("@/pages/Certificates").then((module) => ({
    default: module.Certificates,
  })),
);
const Evidence = React.lazy(() =>
  import("@/pages/Evidence").then((module) => ({ default: module.Evidence })),
);

function RouteFallback() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-5 py-16">
      <LoadingLine>loading the arena…</LoadingLine>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
      <Skeleton className="mt-4 h-64 w-full" />
    </div>
  );
}

function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only rounded-md border border-accent/50 bg-canvas px-3 py-2 font-mono text-[11px] text-accent focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50"
    >
      skip to content
    </a>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={180}>
        <div className="min-h-screen">
          <SkipLink />
          <header className="sticky top-0 z-40 border-b border-line/80 bg-canvas/80 backdrop-blur-xl">
            <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center justify-between px-5">
              <Link to="/" className="flex items-center gap-3 rounded-lg py-1">
                <Logo size={28} />
                <Wordmark />
              </Link>
              <div className="flex items-center gap-3">
                <Link
                  to="/evidence"
                  className="hidden items-center gap-1.5 rounded-md border border-line px-2.5 py-1 font-mono text-[10px] text-muted transition-colors hover:border-accent/45 hover:text-accent sm:inline-flex"
                >
                  <ClipboardList className="h-3 w-3" aria-hidden="true" />
                  evidence
                </Link>
                <Link
                  to="/certificates"
                  className="hidden items-center gap-1.5 rounded-md border border-line px-2.5 py-1 font-mono text-[10px] text-muted transition-colors hover:border-accent/45 hover:text-accent sm:inline-flex"
                >
                  <Hash className="h-3 w-3" aria-hidden="true" />
                  audit records
                </Link>
                <Badge variant="accent">v4 · probe arena</Badge>
                <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-muted lg:block">
                  black-box fairness audit
                </span>
              </div>
            </div>
          </header>
          <main id="main">
            <React.Suspense fallback={<RouteFallback />}>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/audit/:auditId" element={<Arena />} />
                <Route path="/replay/:replayId" element={<Replay />} />
                <Route path="/certificates" element={<Certificates />} />
                <Route path="/evidence" element={<Evidence />} />
              </Routes>
            </React.Suspense>
          </main>
        </div>
      </TooltipProvider>
    </MotionConfig>
  );
}
