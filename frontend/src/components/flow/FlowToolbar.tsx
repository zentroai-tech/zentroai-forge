"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import Image from "next/image";
import toast from "react-hot-toast";
import { useFlowStore } from "@/lib/store";
import { createFlow, updateFlow, createHandoff, deleteHandoff, frontendToBackendIR } from "@/lib/api";
import type { EnginePreference } from "@/types/ir";
import BrandIcon from "@/components/icons/BrandIcon";
import HandoffManagerModal from "./HandoffManagerModal";
import EntrypointsPanel from "./EntrypointsPanel";
import MCPServerManagerModal from "./MCPServerManagerModal";
import IntegrationsLibraryModal from "./IntegrationsLibraryModal";
import AdvancedPolicyPanel from "./AdvancedPolicyPanel";
import AdvancedRetryFallbackPanel from "./AdvancedRetryFallbackPanel";
import AdvancedSchemaPanel from "./AdvancedSchemaPanel";
import SchemaManagerModal from "./SchemaManagerModal";
import IRJsonModal from "./IRJsonModal";
import { Tooltip } from "@/components/ui";

interface FlowToolbarProps {
  onOpenGroup: (group: "run" | "test" | "code", tab?: string) => void;
  onRunFlow: () => void;
  onLogout?: () => void;
}

export default function FlowToolbar({ onOpenGroup, onRunFlow, onLogout }: FlowToolbarProps) {
  const {
    currentFlow,
    selectedAgentId,
    hasUnsavedChanges,
    setCurrentFlow,
    createNewFlow,
    updateFlowMeta,
    markSaved,
    setEntrypoints,
    setFlowPolicies,
    setSchemaContracts,
    setHandoffs,
    updateAgentMeta,
    addHandoff,
    removeHandoff,
  } = useFlowStore();

  const [isLoading, setIsLoading] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isHandoffModalOpen, setIsHandoffModalOpen] = useState(false);
  const [isEntrypointsOpen, setIsEntrypointsOpen] = useState(false);
  const [isMcpModalOpen, setIsMcpModalOpen] = useState(false);
  const [isIntegrationsLibraryOpen, setIsIntegrationsLibraryOpen] = useState(false);
  const [isPolicyOpen, setIsPolicyOpen] = useState(false);
  const [isRetryFallbackOpen, setIsRetryFallbackOpen] = useState(false);
  const [isSchemaOpen, setIsSchemaOpen] = useState(false);
  const [isSchemaManagerOpen, setIsSchemaManagerOpen] = useState(false);
  const [isIrJsonOpen, setIsIrJsonOpen] = useState(false);
  const [isConfigMenuOpen, setIsConfigMenuOpen] = useState(false);
  const [isEngineMenuOpen, setIsEngineMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const configMenuRef = useRef<HTMLDivElement>(null);
  const engineMenuRef = useRef<HTMLDivElement>(null);

  const handleDiscard = useCallback(() => {
    if (!confirm("Discard all changes and start fresh? This cannot be undone.")) {
      return;
    }
    createNewFlow("New Flow");
    toast.success("Started fresh project");
  }, [createNewFlow]);

  const handleSave = useCallback(async (): Promise<boolean> => {
    if (!currentFlow) return false;

    const nodes = currentFlow.nodes || [];
    if (nodes.length === 0) {
      toast.error("Flow must have at least one node. Drag a node from the palette to get started.");
      return false;
    }

    setIsLoading(true);
    try {
      const isExisting = !!currentFlow.created_at;

      let savedFlow;
      if (isExisting) {
        savedFlow = await updateFlow(currentFlow.id, currentFlow);
        toast.success("Flow updated");
      } else {
        try {
          savedFlow = await createFlow(currentFlow);
          toast.success("Flow created");
        } catch (createError) {
          if (createError instanceof Error && createError.message.includes("already exists")) {
            savedFlow = await updateFlow(currentFlow.id, currentFlow);
            toast.success("Flow updated");
          } else {
            throw createError;
          }
        }
      }

      setCurrentFlow(savedFlow);
      markSaved();
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save flow");
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [currentFlow, setCurrentFlow, markSaved]);

  const handleEngineChange = useCallback(
    (engine: EnginePreference) => {
      updateFlowMeta({ engine_preference: engine });
    },
    [updateFlowMeta]
  );

  const handleNameChange = useCallback(
    (name: string) => {
      updateFlowMeta({ name });
    },
    [updateFlowMeta]
  );

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
      if (engineMenuRef.current && !engineMenuRef.current.contains(event.target as Node)) {
        setIsEngineMenuOpen(false);
      }
      if (configMenuRef.current && !configMenuRef.current.contains(event.target as Node)) {
        setIsConfigMenuOpen(false);
      }
    };

    if (isMenuOpen || isEngineMenuOpen || isConfigMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen, isEngineMenuOpen, isConfigMenuOpen]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<"policies" | "retry_fallback" | "schemas" | "ir_json">;
      const target = custom.detail;
      if (target === "policies") setIsPolicyOpen(true);
      if (target === "retry_fallback") setIsRetryFallbackOpen(true);
      if (target === "schemas") setIsSchemaOpen(true);
      if (target === "ir_json") setIsIrJsonOpen(true);
    };
    window.addEventListener("open-system-config", handler as EventListener);
    return () => window.removeEventListener("open-system-config", handler as EventListener);
  }, []);

  const handleMenuAction = useCallback((action: () => void) => {
    action();
    setIsMenuOpen(false);
  }, []);

  return (
    <div
      className="h-16 flex items-center border-b"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      {/* Left section - Logo + Wordmark + Save + flow name */}
      <div className="flex items-center gap-2 pl-3">
        {/* Logo */}
        <Image
          src="/logo.png"
          alt="Zentro Forge"
          width={32}
          height={32}
          className="rounded flex-shrink-0"
        />

        {/* Wordmark */}
        <div className="flex flex-col leading-none mr-1 select-none">
          <span className="text-sm font-bold tracking-tight">
            <span className="text-white">Zentro</span>{" "}
            <span style={{ color: "#23e5c5" }}>Forge</span>
          </span>
          <span className="text-[9px] font-medium tracking-wide" style={{ color: "var(--text-muted)" }}>
            Production-Grade AI Agents
          </span>
        </div>

        <div className="w-px h-5 flex-shrink-0" style={{ backgroundColor: "var(--border-default)" }} />

        <div className="flex items-center gap-1">
          <button
            onClick={handleSave}
            disabled={isLoading || !currentFlow}
            className="btn-secondary flex items-center gap-2 relative"
            title={hasUnsavedChanges ? "Save (unsaved changes)" : "Save"}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
            {isLoading ? "Saving..." : "Save"}
            {hasUnsavedChanges && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber-400" />
            )}
          </button>
          {hasUnsavedChanges && (
            <Tooltip content="Discard all changes" side="bottom">
              <button
                onClick={handleDiscard}
                disabled={isLoading}
                className="btn-secondary p-2"
                style={{ color: "var(--text-muted)" }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "#f87171"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-muted)"; }}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </Tooltip>
          )}
        </div>
        {currentFlow && (
          <input
            type="text"
            value={currentFlow.name}
            onChange={(e) => handleNameChange(e.target.value)}
            className="input-inline w-36"
            placeholder="Flow name"
          />
        )}
      </div>

      {/* Center section - flow config (fills remaining space, right-aligned) */}
      <div className="flex-1 flex items-center gap-3 justify-end pr-4">
        {currentFlow && (
          <>
            {/* Engine selector - minimal */}
            <div className="flex items-center gap-1.5 relative" ref={engineMenuRef}>
              <span className="text-xs text-[var(--text-muted)]">Engine</span>
              <button
                type="button"
                onClick={() => setIsEngineMenuOpen((prev) => !prev)}
                className="select-minimal w-32 flex items-center justify-between"
                style={{
                  backgroundColor: isEngineMenuOpen ? "var(--bg-selected)" : undefined,
                  borderColor: isEngineMenuOpen ? "var(--border-active)" : undefined,
                  color: isEngineMenuOpen ? "var(--text-primary)" : undefined,
                }}
              >
                <span className="flex items-center gap-2">
                  {currentFlow.engine_preference === "langchain" && (
                    <BrandIcon name="langchain" size={14} alt="LangChain" tone="bright" />
                  )}
                  {currentFlow.engine_preference === "llamaindex" && (
                    <BrandIcon name="llamaindex" size={14} alt="LlamaIndex" tone="bright" />
                  )}
                  {currentFlow.engine_preference === "auto" && (
                    <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                      A
                    </span>
                  )}
                  <span>
                    {currentFlow.engine_preference === "langchain" && "LangChain"}
                    {currentFlow.engine_preference === "llamaindex" && "LlamaIndex"}
                    {currentFlow.engine_preference === "auto" && "Auto"}
                  </span>
                </span>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {isEngineMenuOpen && (
                <div
                  className="absolute right-0 top-full mt-1 w-40 rounded-md border z-50 overflow-hidden"
                  style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
                >
                  {(
                    [
                      { value: "langchain", label: "LangChain", icon: <BrandIcon name="langchain" size={14} alt="LangChain" tone="bright" /> },
                      { value: "llamaindex", label: "LlamaIndex", icon: <BrandIcon name="llamaindex" size={14} alt="LlamaIndex" tone="bright" /> },
                      {
                        value: "auto",
                        label: "Auto",
                        icon: (
                          <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                            A
                          </span>
                        ),
                      },
                    ] as const
                  ).map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className="w-full h-9 px-3 text-xs flex items-center gap-2 hover:bg-[var(--bg-tertiary)]"
                      style={{
                        backgroundColor:
                          currentFlow.engine_preference === opt.value ? "var(--bg-selected)" : "transparent",
                        color:
                          currentFlow.engine_preference === opt.value
                            ? "var(--text-primary)"
                            : "var(--text-secondary)",
                      }}
                      onClick={() => {
                        handleEngineChange(opt.value as EnginePreference);
                        setIsEngineMenuOpen(false);
                      }}
                    >
                      {opt.icon}
                      <span>{opt.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {currentFlow.ir_version === "2" && (
              <div className="relative" ref={configMenuRef}>
                <button
                  type="button"
                  onClick={() => setIsConfigMenuOpen((prev) => !prev)}
                  className="btn-secondary text-xs flex items-center gap-1.5"
                  style={
                    isConfigMenuOpen || isEntrypointsOpen || isHandoffModalOpen || isPolicyOpen || isRetryFallbackOpen || isSchemaOpen
                      ? { backgroundColor: "var(--bg-selected)", borderColor: "var(--border-active)", color: "var(--text-primary)" }
                      : undefined
                  }
                >
                  Configure
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {isConfigMenuOpen && (
                  <div
                    className="absolute right-0 top-full mt-1 w-52 rounded-md border z-50 overflow-hidden"
                    style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
                  >
                    {[
                      {
                        label: "Entrypoints",
                        onClick: () => setIsEntrypointsOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M5 12h14M12 5l7 7-7 7" />
                          </svg>
                        ),
                      },
                      {
                        label: "Handoffs",
                        onClick: () => setIsHandoffModalOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                          </svg>
                        ),
                      },
                      {
                        label: "Policies",
                        onClick: () => setIsPolicyOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" />
                          </svg>
                        ),
                      },
                      {
                        label: "Retry/Fallback",
                        onClick: () => setIsRetryFallbackOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        ),
                      },
                      {
                        label: "Schemas",
                        onClick: () => setIsSchemaOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 4h16v16H4z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 8h8M8 12h8M8 16h5" />
                          </svg>
                        ),
                      },
                      {
                        label: "Schema Manager",
                        onClick: () => setIsSchemaManagerOpen(true),
                        icon: (
                          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                          </svg>
                        ),
                      },
                    ].map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        className="w-full h-9 px-3 text-xs text-left flex items-center gap-2.5 hover:bg-[var(--bg-tertiary)] transition-colors"
                        style={{ color: "var(--text-secondary)" }}
                        onClick={() => {
                          item.onClick();
                          setIsConfigMenuOpen(false);
                        }}
                      >
                        <span style={{ color: "var(--text-muted)" }}>{item.icon}</span>
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <Tooltip content="View IR JSON" side="bottom">
              <button
                onClick={() => setIsIrJsonOpen(true)}
                className="btn-secondary"
                style={isIrJsonOpen ? { backgroundColor: "var(--bg-selected)", borderColor: "var(--border-active)", color: "var(--text-primary)" } : undefined}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 6H4v12h4" />
                  <path d="M16 6h4v12h-4" />
                  <path d="M10 9l4 6" />
                  <path d="M14 9l-4 6" />
                </svg>
              </button>
            </Tooltip>
          </>
        )}
      </div>

      {/* Right section - action buttons (w-80 to align with NodeInspector) */}
      <div
        className="w-80 h-full flex items-center gap-2 px-3 border-l flex-shrink-0"
        style={{ borderColor: "var(--border-default)" }}
      >
        {currentFlow && (
          <>
            <button
              onClick={async () => {
                if (!currentFlow.created_at || hasUnsavedChanges) {
                  const ok = await handleSave();
                  if (!ok) return;
                }
                onOpenGroup("test", "chat");
              }}
              className="btn-pill flex items-center gap-2"
              title={!currentFlow.created_at || hasUnsavedChanges ? "Auto-save and open Chat" : "Chat Playground"}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Chat
            </button>

            <button
              onClick={() => onOpenGroup("code", "code")}
              className="btn-pill flex items-center gap-2"
              disabled={!currentFlow.nodes || currentFlow.nodes.length === 0}
              title="Preview generated code"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              Code
            </button>

            <button
              onClick={async () => {
                if (!currentFlow.created_at || hasUnsavedChanges) {
                  const ok = await handleSave();
                  if (!ok) return;
                }
                onRunFlow();
              }}
              className="btn-pill flex items-center gap-2"
              title={!currentFlow.created_at || hasUnsavedChanges ? "Auto-save and run" : "Run the flow"}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Run
            </button>

            {/* Menu dropdown */}
            <div className="relative" ref={menuRef}>
              <Tooltip content="More options" side="bottom">
                <button
                  onClick={() => setIsMenuOpen(!isMenuOpen)}
                  className="btn-secondary"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                  </svg>
                </button>
              </Tooltip>

              {isMenuOpen && (
                <>
                  {/* Backdrop */}
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setIsMenuOpen(false)}
                  />

                  {/* Dropdown menu */}
                  <div
                    className="absolute right-0 top-full mt-2 w-56 rounded-md shadow-lg border z-50"
                    style={{
                      backgroundColor: "var(--bg-secondary)",
                      borderColor: "var(--border-default)",
                    }}
                  >
                    <div className="py-1">
                      {/* MCP Servers */}
                      <button
                        onClick={() => handleMenuAction(() => setIsMcpModalOpen(true))}
                        className="w-full text-left px-4 py-2 text-sm flex items-center gap-3 transition-colors"
                        style={{ color: "var(--text-secondary)" }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--bg-tertiary)";
                          e.currentTarget.style.color = "var(--text-primary)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                          e.currentTarget.style.color = "var(--text-secondary)";
                        }}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                        </svg>
                        <span>MCP Servers</span>
                      </button>
                      {/* Integrations */}
                      <button
                        onClick={() => handleMenuAction(() => setIsIntegrationsLibraryOpen(true))}
                        className="w-full text-left px-4 py-2 text-sm flex items-center gap-3 transition-colors"
                        style={{ color: "var(--text-secondary)" }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--bg-tertiary)";
                          e.currentTarget.style.color = "var(--text-primary)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                          e.currentTarget.style.color = "var(--text-secondary)";
                        }}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
                        </svg>
                        <span>Integrations</span>
                      </button>
                      {/* Divider */}
                      <div className="my-1 border-t" style={{ borderColor: "var(--border-default)" }} />
                      {/* View Runtime Docs */}
                      <a
                        href="https://docs.zentroforge.ai/runtime"
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => setIsMenuOpen(false)}
                        className="w-full text-left px-4 py-2 text-sm flex items-center gap-3 transition-colors"
                        style={{ color: "var(--text-secondary)" }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.backgroundColor = "var(--bg-tertiary)";
                          (e.currentTarget as HTMLElement).style.color = "var(--text-primary)";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
                          (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
                        }}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z" />
                        </svg>
                        <span>View Runtime Docs</span>
                        <svg className="w-3 h-3 ml-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                      {/* Divider */}
                      {onLogout && <div className="my-1 border-t" style={{ borderColor: "var(--border-default)" }} />}
                      {onLogout && (
                        <button
                          onClick={() => handleMenuAction(onLogout)}
                          className="w-full text-left px-4 py-2 text-sm flex items-center gap-3 transition-colors"
                          style={{ color: "var(--text-secondary)" }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = "var(--bg-tertiary)";
                            e.currentTarget.style.color = "var(--text-primary)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = "transparent";
                            e.currentTarget.style.color = "var(--text-secondary)";
                          }}
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h6a2 2 0 012 2v1" />
                          </svg>
                          <span>Logout</span>
                        </button>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
      <HandoffManagerModal
        isOpen={isHandoffModalOpen}
        onClose={() => setIsHandoffModalOpen(false)}
        agents={currentFlow?.agents || []}
        handoffs={currentFlow?.handoffs || []}
        onAdd={async (handoff) => {
          const ok = addHandoff(handoff);
          if (!ok) {
            toast.error("Invalid or duplicate handoff.");
            return;
          }
          if (currentFlow?.created_at && currentFlow?.id) {
            try {
              await createHandoff(currentFlow.id, {
                from_agent_id: handoff.from_agent_id,
                to_agent_id: handoff.to_agent_id,
                mode: handoff.mode,
                guard: handoff.guard
                  ? ({ ...handoff.guard } as unknown as Record<string, unknown>)
                  : null,
                input_schema: handoff.input_schema,
                output_schema: handoff.output_schema,
              });
            } catch (error) {
              removeHandoff((currentFlow.handoffs || []).length);
              toast.error(error instanceof Error ? error.message : "Failed to persist handoff");
              return;
            }
          }
          toast.success("Handoff added");
        }}
        onRemove={async (index) => {
          if (!currentFlow) return;
          const snapshot = currentFlow.handoffs || [];
          removeHandoff(index);
          if (currentFlow.created_at) {
            try {
              await deleteHandoff(currentFlow.id, index);
            } catch (error) {
              setCurrentFlow({ ...currentFlow, handoffs: snapshot });
              toast.error(error instanceof Error ? error.message : "Failed to delete handoff");
              return;
            }
          }
          toast.success("Handoff removed");
        }}
      />
      <EntrypointsPanel
        isOpen={isEntrypointsOpen}
        onClose={() => setIsEntrypointsOpen(false)}
        agents={currentFlow?.agents || []}
        entrypoints={currentFlow?.entrypoints || []}
        onChange={(nextEntrypoints) => {
          setEntrypoints(nextEntrypoints);
        }}
      />
      <MCPServerManagerModal
        isOpen={isMcpModalOpen}
        onClose={() => setIsMcpModalOpen(false)}
      />
      <IntegrationsLibraryModal
        isOpen={isIntegrationsLibraryOpen}
        onClose={() => setIsIntegrationsLibraryOpen(false)}
      />
      {currentFlow?.policies && (
        <AdvancedPolicyPanel
          isOpen={isPolicyOpen}
          onClose={() => setIsPolicyOpen(false)}
          policy={currentFlow.policies}
          onSave={(policies) => {
            setFlowPolicies(policies);
            setIsPolicyOpen(false);
            toast.success("Policy updated");
          }}
        />
      )}
      <AdvancedRetryFallbackPanel
        isOpen={isRetryFallbackOpen}
        onClose={() => setIsRetryFallbackOpen(false)}
        agents={currentFlow?.agents || []}
        selectedAgentId={selectedAgentId}
        onSave={(agentId, retries, fallbacks) => {
          const updated = updateAgentMeta(agentId, { retries, fallbacks });
          if (!updated) {
            toast.error("Failed to update agent retry/fallback.");
            return;
          }
          setIsRetryFallbackOpen(false);
          toast.success("Retry/fallback updated");
        }}
      />
      <AdvancedSchemaPanel
        isOpen={isSchemaOpen}
        onClose={() => setIsSchemaOpen(false)}
        handoffs={currentFlow?.handoffs || []}
        schemaContracts={currentFlow?.resources?.schema_contracts || {}}
        onOpenSchemaManager={() => setIsSchemaManagerOpen(true)}
        onSave={(handoffs) => {
          setHandoffs(handoffs);
          setIsSchemaOpen(false);
          toast.success("Schema contracts updated");
        }}
      />
      <SchemaManagerModal
        isOpen={isSchemaManagerOpen}
        onClose={() => setIsSchemaManagerOpen(false)}
        schemas={currentFlow?.resources?.schema_contracts || {}}
        onSave={(schemas) => {
          setSchemaContracts(schemas);
          toast.success("Schemas updated");
        }}
      />
      <IRJsonModal
        isOpen={isIrJsonOpen}
        onClose={() => setIsIrJsonOpen(false)}
        ir={currentFlow ? frontendToBackendIR(currentFlow) : null}
      />
    </div>
  );
}
