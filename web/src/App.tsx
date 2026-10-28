import { Link, Route, Routes } from "react-router-dom";

import { Logo, Wordmark } from "@/components/Logo";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Landing } from "@/pages/Landing";
import { Arena } from "@/pages/Arena";

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
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/audit/:auditId" element={<Arena />} />
          </Routes>
        </main>
      </div>
    </TooltipProvider>
  );
}
