import { cn } from "@/lib/utils";

export function Logo({ className, size = 30 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      <rect x="1" y="1" width="30" height="30" rx="9" stroke="#5EEAD4" strokeOpacity="0.45" />
      <circle cx="14.2" cy="14.2" r="6.2" stroke="#5EEAD4" strokeWidth="1.6" />
      <path d="M18.9 18.9L24.2 24.2" stroke="#5EEAD4" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="14.2" cy="14.2" r="1.6" fill="#5EEAD4" />
      <path d="M5 24.5H10.5" stroke="#5EEAD4" strokeOpacity="0.35" strokeWidth="1.2" />
      <path d="M21.5 24.5H27" stroke="#5EEAD4" strokeOpacity="0.35" strokeWidth="1.2" />
    </svg>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-baseline gap-2">
      <span className="text-[17px] font-semibold tracking-[-0.02em]">FairLens</span>
      {!compact && (
        <span className="font-mono text-[9px] uppercase tracking-[0.24em] text-accent">
          probe arena
        </span>
      )}
    </span>
  );
}
