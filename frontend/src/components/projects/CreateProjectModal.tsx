"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { listTemplates, createProjectFromTemplate, getFlow } from "@/lib/api";
import { useFlowStore } from "@/lib/store";
import type { TemplateDTO, TemplateParam, Engine } from "@/types/template";
import TemplateCard from "./TemplateCard";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProjectCreated: () => void;
}

export default function CreateProjectModal({
  isOpen,
  onClose,
  onProjectCreated,
}: CreateProjectModalProps) {
  const { setCurrentFlow, markSaved } = useFlowStore();
  const [templates, setTemplates] = useState<TemplateDTO[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);

  // Selection state
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [engineSelections, setEngineSelections] = useState<Record<string, Engine>>({});
  const [projectName, setProjectName] = useState("");
  // Per-template param values keyed by template_id → { param_name: value }
  const [paramValues, setParamValues] = useState<Record<string, Record<string, unknown>>>({});

  // Validation
  const [errors, setErrors] = useState<{ name?: string; template?: string }>({});

  // Load templates
  const loadTemplates = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listTemplates();
      setTemplates(data);
      // Initialize engine selections and param defaults
      const defaultEngines: Record<string, Engine> = {};
      const defaultParams: Record<string, Record<string, unknown>> = {};
      data.forEach((t) => {
        defaultEngines[t.id] = t.default_engine;
        const pDefaults: Record<string, unknown> = {};
        (t.params || []).forEach((p) => { pDefaults[p.name] = p.default; });
        defaultParams[t.id] = pDefaults;
      });
      setEngineSelections(defaultEngines);
      setParamValues(defaultParams);
    } catch (error) {
      toast.error("Failed to load templates");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadTemplates();
      setProjectName("");
      setSelectedTemplateId(null);
      setErrors({});
    }
  }, [isOpen, loadTemplates]);

  const setParamValue = (templateId: string, paramName: string, value: unknown) => {
    setParamValues((prev) => ({
      ...prev,
      [templateId]: { ...(prev[templateId] ?? {}), [paramName]: value },
    }));
  };

  const renderParamInput = (param: TemplateParam, templateId: string) => {
    const value = (paramValues[templateId] ?? {})[param.name] ?? param.default;

    if (param.type === "select" && param.options) {
      return (
        <select
          value={String(value)}
          onChange={(e) => setParamValue(templateId, param.name, e.target.value)}
          className="w-full rounded-md px-2 py-1 text-sm text-white border border-[var(--border-default)] bg-[var(--bg-primary)] focus:outline-none focus:border-cyan-500"
          disabled={isCreating}
        >
          {param.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    }

    if (param.type === "boolean") {
      return (
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => setParamValue(templateId, param.name, e.target.checked)}
          className="w-4 h-4 rounded accent-cyan-500"
          disabled={isCreating}
        />
      );
    }

    if (param.type === "integer") {
      return (
        <input
          type="number"
          value={Number(value)}
          onChange={(e) => setParamValue(templateId, param.name, parseInt(e.target.value, 10))}
          className="w-full rounded-md px-2 py-1 text-sm text-white border border-[var(--border-default)] bg-[var(--bg-primary)] focus:outline-none focus:border-cyan-500"
          disabled={isCreating}
        />
      );
    }

    // string
    return (
      <input
        type="text"
        value={String(value ?? "")}
        onChange={(e) => setParamValue(templateId, param.name, e.target.value)}
        className="w-full rounded-md px-2 py-1 text-sm text-white border border-[var(--border-default)] bg-[var(--bg-primary)] focus:outline-none focus:border-cyan-500"
        disabled={isCreating}
      />
    );
  };

  const validate = (): boolean => {
    const newErrors: { name?: string; template?: string } = {};

    if (!projectName.trim()) {
      newErrors.name = "Project name is required";
    }
    if (!selectedTemplateId) {
      newErrors.template = "Please select a template";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleCreate = async () => {
    if (!validate() || !selectedTemplateId) return;

    setIsCreating(true);
    try {
      const engine = engineSelections[selectedTemplateId];
      const params = paramValues[selectedTemplateId] ?? {};
      const response = await createProjectFromTemplate({
        name: projectName.trim(),
        template_id: selectedTemplateId,
        engine,
        params: Object.keys(params).length > 0 ? params : undefined,
      });

      // Load the created project with its IR
      const flow = await getFlow(response.id);
      setCurrentFlow(flow);
      markSaved();

      toast.success(`Project "${projectName}" created`);
      onProjectCreated();
      onClose();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create project");
    } finally {
      setIsCreating(false);
    }
  };

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Create New Project</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
            disabled={isCreating}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <svg className="w-6 h-6 text-[var(--text-muted)] animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="ml-2 text-[var(--text-muted)]">Loading templates...</span>
            </div>
          ) : (
            <>
              {/* Project Name */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => {
                    setProjectName(e.target.value);
                    if (errors.name) setErrors((prev) => ({ ...prev, name: undefined }));
                  }}
                  placeholder="My Awesome Agent"
                  className={`input-field w-full ${errors.name ? "border-red-500" : ""}`}
                  disabled={isCreating}
                />
                {errors.name && (
                  <p className="text-xs text-red-400 mt-1">{errors.name}</p>
                )}
              </div>

              {/* Template Selection */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                  Choose a Template
                </label>
                {errors.template && (
                  <p className="text-xs text-red-400 mb-2">{errors.template}</p>
                )}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {templates.map((template) => (
                    <TemplateCard
                      key={template.id}
                      template={template}
                      isSelected={selectedTemplateId === template.id}
                      selectedEngine={engineSelections[template.id] || template.default_engine}
                      onSelect={() => {
                        setSelectedTemplateId(template.id);
                        if (errors.template) setErrors((prev) => ({ ...prev, template: undefined }));
                      }}
                      onEngineChange={(engine) => {
                        setEngineSelections((prev) => ({ ...prev, [template.id]: engine }));
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Template Options — shown when selected template has configurable params */}
              {selectedTemplate && (selectedTemplate.params || []).length > 0 && (
                <div
                  className="mb-6 rounded-xl p-4 border"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    borderColor: "var(--border-default)",
                  }}
                >
                  <h3 className="text-sm font-medium text-white mb-3">Template Options</h3>
                  <div className="space-y-3">
                    {(selectedTemplate.params || []).map((param) => (
                      <div key={param.name} className="flex items-center gap-3">
                        <div className="flex-1 min-w-0">
                          <label className="block text-xs font-medium text-[var(--text-secondary)] mb-0.5">
                            {param.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                          </label>
                          <p className="text-xs text-[var(--text-muted)] truncate">{param.description}</p>
                        </div>
                        <div className={param.type === "boolean" ? "flex items-center" : "w-40 shrink-0"}>
                          {renderParamInput(param, selectedTemplate.id)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary Panel */}
              {selectedTemplate && (
                <div
                  className="rounded-xl p-4 border"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    borderColor: "var(--border-default)",
                  }}
                >
                  <h3 className="text-sm font-medium text-white mb-2">Project Summary</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-[var(--text-muted)]">Template:</span>
                      <span className="ml-2 text-[var(--text-secondary)]">{selectedTemplate.name}</span>
                    </div>
                    <div>
                      <span className="text-[var(--text-muted)]">Engine:</span>
                      <span className="ml-2 text-[var(--text-secondary)] capitalize">
                        {engineSelections[selectedTemplate.id] === "langgraph" ? "LangGraph" : "LlamaIndex"}
                      </span>
                    </div>
                    {projectName && (
                      <div className="col-span-2">
                        <span className="text-[var(--text-muted)]">Name:</span>
                        <span className="ml-2 text-white font-medium">{projectName}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div
          className="p-4 border-t flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <p className="text-xs text-[var(--text-muted)]">
            {selectedTemplate
              ? `${selectedTemplate.name} will be initialized with ${
                  selectedTemplate.preview_type === "blank" ? "an empty canvas" : "a pre-built graph"
                }`
              : "Select a template to continue"}
          </p>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-pill" disabled={isCreating}>
              Cancel
            </button>
            <button
              onClick={handleCreate}
              className="btn-pill"
              disabled={isCreating || !selectedTemplateId || !projectName.trim()}
            >
              {isCreating ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating...
                </span>
              ) : (
                "Create Project"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
