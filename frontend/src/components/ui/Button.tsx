"use client";

import React from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "pill";
type Size = "sm" | "md";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  active?: boolean;
  loading?: boolean;
}

const variantClass: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-secondary",
  danger: "btn-danger",
  pill: "btn-pill",
};

export function Button({
  variant = "secondary",
  size = "md",
  active = false,
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        variantClass[variant],
        active && variant === "pill" && "active",
        size === "sm" && "!px-2 !py-1 !text-[11px]",
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? "Loading…" : children}
    </button>
  );
}
