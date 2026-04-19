"use client";

import type { Engine } from "@/types/template";
import BrandIcon from "@/components/icons/BrandIcon";

interface EngineSelectorProps {
  value: Engine;
  onChange: (engine: Engine) => void;
  supportedEngines: Engine[];
  disabled?: boolean;
}

const ENGINE_INFO: Record<Engine, { label: string; icon: React.ReactNode; color: string }> = {
  llamaindex: {
    label: "LlamaIndex",
    color: "#7c3aed",
    icon: <BrandIcon name="llamaindex" size={16} alt="LlamaIndex" />,
  },
  langgraph: {
    label: "LangGraph",
    color: "#059669",
    icon: <BrandIcon name="langgraph" size={16} alt="LangGraph" />,
  },
};

export default function EngineSelector({
  value,
  onChange,
  supportedEngines,
  disabled = false,
}: EngineSelectorProps) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-[var(--border-default)]">
      {supportedEngines.map((engine) => {
        const info = ENGINE_INFO[engine];
        const isSelected = value === engine;

        return (
          <button
            key={engine}
            onClick={() => onChange(engine)}
            disabled={disabled}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium transition-all ${
              isSelected
                ? "text-white"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
            style={{
              backgroundColor: isSelected ? `${info.color}30` : "var(--bg-tertiary)",
              color: isSelected ? info.color : undefined,
            }}
          >
            <span style={{ color: isSelected ? info.color : undefined }}>{info.icon}</span>
            {info.label}
          </button>
        );
      })}
    </div>
  );
}
