"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface LabelProps {
  children: React.ReactNode;
  muted?: boolean;
  uppercase?: boolean;
  className?: string;
}

export function Label({ children, muted = false, uppercase = false, className }: LabelProps) {
  return (
    <span
      className={cn(
        "text-[10px] font-medium",
        muted ? "text-[var(--text-muted)]" : "text-[var(--text-secondary)]",
        uppercase && "uppercase tracking-widest",
        className
      )}
    >
      {children}
    </span>
  );
}
