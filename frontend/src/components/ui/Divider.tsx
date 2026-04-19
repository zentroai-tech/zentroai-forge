"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface DividerProps {
  label?: string;
  className?: string;
}

export function Divider({ label, className }: DividerProps) {
  if (label) {
    return (
      <div className={cn("flex items-center gap-2 pt-2 pb-0.5", className)}>
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {label}
        </span>
        <div className="flex-1 h-px bg-[var(--border-subtle)]" />
      </div>
    );
  }

  return <div className={cn("h-px bg-[var(--border-subtle)] my-2", className)} />;
}
