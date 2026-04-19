"use client";

import Image from "next/image";

type BrandName =
  | "openai"
  | "claude"
  | "gemini"
  | "langchain"
  | "llamaindex"
  | "langgraph"
  | "mcp";

const BRAND_ICON_PATHS: Record<BrandName, string> = {
  openai: "/icons/openai.svg",
  claude: "/icons/claude.svg",
  gemini: "/icons/gemini.svg",
  langchain: "/icons/langchain.svg",
  llamaindex: "/icons/llamaindex.svg",
  langgraph: "/icons/langgraph.svg",
  mcp: "/icons/mcp.svg",
};

interface BrandIconProps {
  name: BrandName;
  size?: number;
  className?: string;
  alt?: string;
  tone?: "muted" | "bright" | "none";
}

export default function BrandIcon({ name, size = 16, className, alt, tone = "muted" }: BrandIconProps) {
  const filterByTone: Record<NonNullable<BrandIconProps["tone"]>, string | undefined> = {
    muted: "brightness(0) saturate(100%) invert(76%) sepia(9%) saturate(519%) hue-rotate(178deg) brightness(94%) contrast(90%)",
    bright: "brightness(0) saturate(100%) invert(94%) sepia(12%) saturate(491%) hue-rotate(184deg) brightness(105%) contrast(98%)",
    none: undefined,
  };

  return (
    <Image
      src={BRAND_ICON_PATHS[name]}
      width={size}
      height={size}
      alt={alt || `${name} icon`}
      className={className}
      style={{ filter: filterByTone[tone] }}
    />
  );
}
