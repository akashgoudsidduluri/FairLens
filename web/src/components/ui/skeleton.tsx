import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Loading placeholders shared by every page.
 *
 * Skeletons keep the page geometry stable while an API response is in flight,
 * so content does not jump when the real rows arrive. They are decorative: the
 * visible loading sentence carries the status for assistive technology.
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded bg-line/50", className)}
      {...props}
    />
  );
}

export function SkeletonText({
  lines = 2,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className={cn(
            "h-2.5 animate-pulse rounded bg-line/40",
            index === lines - 1 ? "w-2/3" : "w-full",
          )}
        />
      ))}
    </div>
  );
}

export function CardSkeleton({
  className,
  lines = 3,
}: {
  className?: string;
  lines?: number;
}) {
  return (
    <div
      className={cn("panel p-4", className)}
      aria-hidden="true"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-2.5 w-16" />
          <Skeleton className="h-4 w-2/3" />
        </div>
        <Skeleton className="h-5 w-20 shrink-0" />
      </div>
      <SkeletonText lines={lines} className="mt-4" />
    </div>
  );
}

export function LoadingLine({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-2 font-mono text-[10.5px] text-muted",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 animate-pulse-line rounded-full bg-accent"
      />
      {children}
    </p>
  );
}
