"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps {
  label: string;
  color: string;       // hex — generates 13% opacity bg automatically
  variant?: "fill" | "outline";
  size?: "xs" | "sm";
}

export function Badge({ label, color, variant = "fill", size = "xs" }: BadgeProps) {
  const sizeClass = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-1.5 py-0.5 text-[10px]";

  if (variant === "outline") {
    return (
      <span
        className={cn("rounded font-medium border", sizeClass)}
        style={{ borderColor: color + "66", color }}
      >
        {label}
      </span>
    );
  }

  return (
    <span
      className={cn("rounded font-medium", sizeClass)}
      style={{ backgroundColor: color + "22", color }}
    >
      {label}
    </span>
  );
}
