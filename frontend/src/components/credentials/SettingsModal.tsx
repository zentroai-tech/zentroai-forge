"use client";

import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import CredentialsList from "./CredentialsList";
import EnvManager from "./EnvManager";
import { getGitOpsStatus, connectGitHub, disconnectGitHub } from "@/lib/api";
import type { GitOpsBackendStatus } from "@/types/gitops";

type SettingsTab = "credentials" | "environment" | "github";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  scope: "workspace" | "project";
  projectId?: string;
}

export default function SettingsModal({
  isOpen,
  onClose,
  scope,
  projectId,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>("credentials");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-4xl mx-4 max-h-[85vh] flex flex-col"
        style={{
          backgroundColor: "var(--bg-secondary)",
          border: "1px solid var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">
              {scope === "workspace" ? "Workspace" : "Project"} Settings
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <div
            className="w-48 p-4 border-r overflow-y-auto"
            style={{
              backgroundColor: "var(--bg-primary)",
              borderColor: "var(--border-default)",
            }}
          >
            <nav className="space-y-1">
              <button
                onClick={() => setActiveTab("credentials")}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "credentials"
                    ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                Credentials
              </button>

              <button
                onClick={() => setActiveTab("environment")}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "environment"
                    ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
                Environment
              </button>

              <button
                onClick={() => setActiveTab("github")}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "github"
                    ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                }`}
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
                GitHub
              </button>
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto" style={{ backgroundColor: "var(--bg-primary)" }}>
            {activeTab === "credentials" && (
              <CredentialsList scope={scope} projectId={projectId} />
            )}
            {activeTab === "environment" && (
              <EnvManager flowId={projectId} />
            )}
            {activeTab === "github" && (
              <GitHubSettings />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function GitHubSettings() {
  const [status, setStatus] = useState<GitOpsBackendStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [patInput, setPatInput] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  useEffect(() => {
    checkStatus();
  }, []);

  async function checkStatus() {
    setIsLoading(true);
    try {
      const result = await getGitOpsStatus();
      setStatus(result);
    } catch {
      setStatus({ configured: false });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleConnect() {
    if (!patInput.trim()) return;
    setIsConnecting(true);
    try {
      const result = await connectGitHub(patInput.trim());
      setStatus({ configured: true, username: result.username });
      setPatInput("");
      toast.success(`Connected as @${result.username}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to connect");
    } finally {
      setIsConnecting(false);
    }
  }

  async function handleDisconnect() {
    setIsDisconnecting(true);
    try {
      await disconnectGitHub();
      setStatus({ configured: false });
      toast.success("GitHub disconnected");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to disconnect");
    } finally {
      setIsDisconnecting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-[var(--text-muted)]">
        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Checking GitHub status...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-white font-medium mb-1">GitHub Integration</h3>
        <p className="text-sm text-[var(--text-muted)]">
          Connect your GitHub account to create pull requests from exported agent code.
        </p>
      </div>

      {status?.configured ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-lg border" style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)" }}>
            <div className="w-10 h-10 rounded-full bg-green-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
            </div>
            <div className="flex-1">
              <p className="text-sm text-white font-medium">Connected{status.username ? ` as @${status.username}` : ""}</p>
              <p className="text-xs text-[var(--text-muted)]">You can create pull requests from the Code & Versions tab.</p>
            </div>
            <button
              onClick={handleDisconnect}
              disabled={isDisconnecting}
              className="px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 rounded-lg transition-colors border border-red-500/20"
            >
              {isDisconnecting ? "Disconnecting..." : "Disconnect"}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div
            className="rounded-lg p-3 text-xs space-y-2"
            style={{ backgroundColor: "var(--bg-tertiary)" }}
          >
            <p className="text-[var(--text-secondary)] font-medium">How to create a token:</p>
            <ol className="list-decimal list-inside space-y-1 text-[var(--text-muted)]">
              <li>Go to <a href="https://github.com/settings/tokens/new" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">GitHub Token Settings</a></li>
              <li>Give it a descriptive name (e.g. &quot;Zentro Forge&quot;)</li>
              <li>Select the <code className="bg-[var(--bg-secondary)] px-1 py-0.5 rounded">repo</code> scope (full control of private repositories)</li>
              <li>Click <strong className="text-[var(--text-secondary)]">Generate token</strong> and copy it below</li>
            </ol>
          </div>

          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              Personal Access Token
            </label>
            <input
              type="password"
              value={patInput}
              onChange={(e) => setPatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              className="input-field w-full"
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
            />
          </div>

          <button
            onClick={handleConnect}
            disabled={isConnecting || !patInput.trim()}
            className="btn-pill"
          >
            {isConnecting ? (
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Connecting...
              </span>
            ) : (
              "Connect to GitHub"
            )}
          </button>
        </div>
      )}
    </div>
  );
}
