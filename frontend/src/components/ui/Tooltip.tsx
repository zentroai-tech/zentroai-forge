"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: string;
  side?: "top" | "bottom" | "left" | "right";
  children: React.ReactNode;
}

const sideClasses: Record<NonNullable<TooltipProps["side"]>, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
  left: "right-full top-1/2 -translate-y-1/2 mr-1.5",
  right: "left-full top-1/2 -translate-y-1/2 ml-1.5",
};

export function Tooltip({ content, side = "top", children }: TooltipProps) {
  return (
    <span className="relative group inline-flex">
      {children}
      <span
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded px-2 py-1",
          "text-[10px] font-medium",
          "bg-[var(--bg-elevated)] text-[var(--text-primary)]",
          "border border-[var(--border-default)]",
          "opacity-0 group-hover:opacity-100 transition-opacity duration-150",
          sideClasses[side]
        )}
      >
        {content}
      </span>
    </span>
  );
}
