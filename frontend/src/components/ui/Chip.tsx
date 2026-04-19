"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

export function Chip({ active = false, className, children, ...props }: ChipProps) {
  return (
    <button
      type="button"
      className={cn("chip-option", active && "active", className)}
      {...props}
    >
      {children}
    </button>
  );
}
