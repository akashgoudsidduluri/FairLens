import * as React from "react";
import { Link, Route, Routes } from "react-router-dom";

import { Logo, Wordmark } from "@/components/Logo";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";

// Recharts and the arena only load once a visitor leaves the library.
const Landing = React.lazy(() =>
  import("@/pages/Landing").then((module) => ({ default: module.Landing })),
);
const Arena = React.lazy(() =>
  import("@/pages/Arena").then((module) => ({ default: module.Arena })),
);

function RouteFallback() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] items-center gap-2 px-5 py-24 font-mono text-[11px] text-muted">
      <span className="h-1.5 w-1.5 animate-pulse-line rounded-full bg-accent" />
      loading the arena…
    </div>
  );
}

export default function App() {
  return (
    <TooltipProvider delayDuration={180}>
      <div className="min-h-screen">
        <header className="sticky top-0 z-40 border-b border-line/80 bg-canvas/80 backdrop-blur-xl">
          <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center justify-between px-5">
            <Link to="/" className="flex items-center gap-3 rounded-lg py-1">
              <Logo size={28} />
              <Wordmark />
            </Link>
            <div className="flex items-center gap-3">
              <Badge variant="accent">v4 · probe arena</Badge>
              <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-muted sm:block">
                black-box fairness audit
              </span>
            </div>
          </div>
        </header>
        <main>
          <React.Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/audit/:auditId" element={<Arena />} />
            </Routes>
          </React.Suspense>
        </main>
      </div>
    </TooltipProvider>
  );
}
