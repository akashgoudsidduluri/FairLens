import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.12em]",
  {
    variants: {
      variant: {
        default: "border-line bg-raised text-muted",
        accent: "border-accent/35 bg-accent/10 text-accent",
        ok: "border-ok/35 bg-ok/10 text-ok",
        danger: "border-danger/35 bg-danger/10 text-danger",
        warn: "border-warn/35 bg-warn/10 text-warn",
        outline: "border-line bg-transparent text-muted",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
