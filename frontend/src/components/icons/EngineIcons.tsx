"use client";

import { memo } from "react";
import BrandIcon from "./BrandIcon";

interface IconProps {
  className?: string;
  size?: number;
}

export const LangChainIcon = memo(function LangChainIcon({ className, size = 16 }: IconProps) {
  return <BrandIcon name="langchain" size={size} className={className} alt="LangChain" />;
});

export const LlamaIndexIcon = memo(function LlamaIndexIcon({ className, size = 16 }: IconProps) {
  return <BrandIcon name="llamaindex" size={size} className={className} alt="LlamaIndex" />;
});

export const AutoEngineIcon = memo(function AutoEngineIcon({ className, size = 16 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="12" cy="12" r="10" fill="#6366F1" />
      <path
        d="M12 6V8M12 16V18M6 12H8M16 12H18M8.46 8.46L9.88 9.88M14.12 14.12L15.54 15.54M8.46 15.54L9.88 14.12M14.12 9.88L15.54 8.46"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="2" fill="white" />
    </svg>
  );
});

export function getEngineIcon(engine: string | null | undefined, size?: number) {
  switch (engine) {
    case "langchain":
      return <LangChainIcon size={size} />;
    case "llamaindex":
      return <LlamaIndexIcon size={size} />;
    case "auto":
      return <AutoEngineIcon size={size} />;
    default:
      return null;
  }
}
