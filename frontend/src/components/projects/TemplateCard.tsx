"use client";

import type { TemplateDTO, Engine } from "@/types/template";
import EngineSelector from "./EngineSelector";

interface TemplateCardProps {
  template: TemplateDTO;
  isSelected: boolean;
  selectedEngine: Engine;
  onSelect: () => void;
  onEngineChange: (engine: Engine) => void;
}

// Mini preview diagrams for each template type
function BlankPreview() {
  return (
    <div className="w-full h-24 rounded-lg bg-[var(--bg-primary)] border border-dashed border-[var(--border-default)] flex items-center justify-center">
      <div className="text-center">
        <svg className="w-8 h-8 mx-auto text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
        </svg>
        <p className="text-xs text-[var(--text-muted)] mt-1">Empty Canvas</p>
      </div>
    </div>
  );
}

function RAGPreview() {
  return (
    <div className="w-full h-24 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-default)] p-3 overflow-hidden">
      <svg viewBox="0 0 200 60" className="w-full h-full">
        {/* Retriever Node */}
        <rect x="5" y="20" width="40" height="20" rx="4" fill="#3b82f620" stroke="#3b82f6" strokeWidth="1" />
        <text x="25" y="33" textAnchor="middle" fill="#3b82f6" fontSize="6" fontWeight="500">Retrieve</text>

        {/* Arrow */}
        <path d="M48 30 L58 30" stroke="#6b7280" strokeWidth="1" markerEnd="url(#arrowhead)" />

        {/* Guard/Router Node */}
        <rect x="60" y="20" width="40" height="20" rx="4" fill="#10b98120" stroke="#10b981" strokeWidth="1" />
        <text x="80" y="33" textAnchor="middle" fill="#10b981" fontSize="6" fontWeight="500">Guard</text>

        {/* Branching arrows */}
        <path d="M103 25 L115 15" stroke="#6b7280" strokeWidth="1" />
        <path d="M103 35 L115 45" stroke="#6b7280" strokeWidth="1" />

        {/* LLM Node */}
        <rect x="118" y="5" width="35" height="20" rx="4" fill="#8b5cf620" stroke="#8b5cf6" strokeWidth="1" />
        <text x="135" y="18" textAnchor="middle" fill="#8b5cf6" fontSize="6" fontWeight="500">LLM</text>

        {/* Abstain Node */}
        <rect x="118" y="35" width="35" height="20" rx="4" fill="#f5990b20" stroke="#f59e0b" strokeWidth="1" />
        <text x="135" y="48" textAnchor="middle" fill="#f59e0b" fontSize="6" fontWeight="500">Abstain</text>

        {/* Output arrows */}
        <path d="M155 15 L170 25" stroke="#6b7280" strokeWidth="1" />
        <path d="M155 45 L170 35" stroke="#6b7280" strokeWidth="1" />

        {/* Output Node */}
        <rect x="172" y="20" width="25" height="20" rx="4" fill="#6366f120" stroke="#6366f1" strokeWidth="1" />
        <text x="184" y="33" textAnchor="middle" fill="#6366f1" fontSize="5" fontWeight="500">Output</text>

        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#6b7280" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function SimpleAgentPreview() {
  return (
    <div className="w-full h-24 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-default)] p-3 overflow-hidden">
      <svg viewBox="0 0 200 60" className="w-full h-full">
        {/* LLM Node */}
        <rect x="20" y="20" width="45" height="20" rx="4" fill="#8b5cf620" stroke="#8b5cf6" strokeWidth="1" />
        <text x="42" y="33" textAnchor="middle" fill="#8b5cf6" fontSize="6" fontWeight="500">LLM Agent</text>

        {/* Arrow to Tool */}
        <path d="M68 30 L90 30" stroke="#6b7280" strokeWidth="1" markerEnd="url(#arrowhead2)" />

        {/* Tool Node */}
        <rect x="93" y="20" width="35" height="20" rx="4" fill="#f5990b20" stroke="#f59e0b" strokeWidth="1" />
        <text x="110" y="33" textAnchor="middle" fill="#f59e0b" fontSize="6" fontWeight="500">Tools</text>

        {/* Arrow to Output */}
        <path d="M130 30 L150 30" stroke="#6b7280" strokeWidth="1" markerEnd="url(#arrowhead2)" />

        {/* Output Node */}
        <rect x="153" y="20" width="30" height="20" rx="4" fill="#6366f120" stroke="#6366f1" strokeWidth="1" />
        <text x="168" y="33" textAnchor="middle" fill="#6366f1" fontSize="5" fontWeight="500">Output</text>

        {/* Loop back arrow */}
        <path d="M110 42 C110 55, 42 55, 42 42" stroke="#6b7280" strokeWidth="1" strokeDasharray="3" fill="none" markerEnd="url(#arrowhead2)" />

        <defs>
          <marker id="arrowhead2" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#6b7280" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function SupervisorWorkersPreview() {
  return (
    <div className="w-full h-24 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-default)] p-3 overflow-hidden">
      <svg viewBox="0 0 200 60" className="w-full h-full">
        <defs>
          <marker id="arrowhead-supervisor" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#6b7280" />
          </marker>
        </defs>

        {/* Supervisor */}
        <rect x="78" y="4" width="44" height="16" rx="4" fill="#0ea5e920" stroke="#0ea5e9" strokeWidth="1" />
        <text x="100" y="15" textAnchor="middle" fill="#0ea5e9" fontSize="5.5" fontWeight="500">Supervisor</text>

        {/* Workers */}
        <rect x="32" y="38" width="44" height="16" rx="4" fill="#10b98120" stroke="#10b981" strokeWidth="1" />
        <text x="54" y="49" textAnchor="middle" fill="#10b981" fontSize="5.5" fontWeight="500">Worker A</text>

        <rect x="124" y="38" width="44" height="16" rx="4" fill="#a855f720" stroke="#a855f7" strokeWidth="1" />
        <text x="146" y="49" textAnchor="middle" fill="#a855f7" fontSize="5.5" fontWeight="500">Worker B</text>

        {/* Handoffs */}
        <path d="M88 20 L62 37" stroke="#6b7280" strokeWidth="1" markerEnd="url(#arrowhead-supervisor)" />
        <path d="M112 20 L138 37" stroke="#6b7280" strokeWidth="1" markerEnd="url(#arrowhead-supervisor)" />
        <path d="M62 38 Q88 28 96 20" stroke="#6b7280" strokeWidth="1" strokeDasharray="2 2" fill="none" />
        <path d="M138 38 Q112 28 104 20" stroke="#6b7280" strokeWidth="1" strokeDasharray="2 2" fill="none" />
      </svg>
    </div>
  );
}

const PREVIEW_COMPONENTS: Record<string, React.ComponentType> = {
  blank: BlankPreview,
  rag: RAGPreview,
  simple_agent: SimpleAgentPreview,
  supervisor_workers: SupervisorWorkersPreview,
};

export default function TemplateCard({
  template,
  isSelected,
  selectedEngine,
  onSelect,
  onEngineChange,
}: TemplateCardProps) {
  const PreviewComponent = PREVIEW_COMPONENTS[template.preview_type] || BlankPreview;

  return (
    <div
      className={`rounded-xl border-2 p-4 transition-all cursor-pointer ${
        isSelected
          ? "border-cyan-500 bg-cyan-500/5"
          : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
      }`}
      style={{ backgroundColor: isSelected ? undefined : "var(--bg-secondary)" }}
      onClick={onSelect}
    >
      {/* Preview */}
      <div className="mb-4">
        <PreviewComponent />
      </div>

      {/* Title & Description */}
      <h3 className="text-base font-semibold text-white mb-1">{template.name}</h3>
      <p className="text-sm text-[var(--text-muted)] mb-3 line-clamp-2">{template.description}</p>

      {/* Tags */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {template.tags.map((tag, i) => (
          <span
            key={i}
            className="px-2 py-0.5 text-xs rounded-full"
            style={{
              backgroundColor: `${tag.color}20`,
              color: tag.color,
            }}
          >
            {tag.label}
          </span>
        ))}
      </div>

      {/* Engine Selector */}
      <div onClick={(e) => e.stopPropagation()}>
        <EngineSelector
          value={selectedEngine}
          onChange={onEngineChange}
          supportedEngines={template.supported_engines}
        />
      </div>

      {/* Selected indicator */}
      {isSelected && (
        <div className="mt-4 flex items-center justify-center gap-2 text-[var(--text-primary)] text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Selected
        </div>
      )}
    </div>
  );
}
