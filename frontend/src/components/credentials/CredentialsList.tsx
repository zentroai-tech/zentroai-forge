"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import type {
  Credential,
  CredentialScopeType,
  CreateCredentialRequest,
} from "@/types/credentials";
import { PROVIDER_INFO } from "@/types/credentials";
import {
  listCredentials,
  createCredential,
  updateCredential,
  deleteCredential,
  testCredential,
} from "@/lib/api";
import CredentialCard from "./CredentialCard";
import CredentialForm from "./CredentialForm";

interface CredentialsListProps {
  scope: CredentialScopeType;
  projectId?: string;
}

export default function CredentialsList({ scope, projectId }: CredentialsListProps) {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const [apiAvailable, setApiAvailable] = useState(true);

  const loadCredentials = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listCredentials(scope, projectId);
      setCredentials(data);
      setApiAvailable(true);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "";
      if (errorMessage.includes("404") || errorMessage.toLowerCase().includes("not found")) {
        // API not implemented yet - show empty state without error
        setCredentials([]);
        setApiAvailable(false);
      } else {
        toast.error("Failed to load credentials");
      }
    } finally {
      setIsLoading(false);
    }
  }, [scope, projectId]);

  useEffect(() => {
    loadCredentials();
  }, [loadCredentials]);

  const handleCreate = async (data: CreateCredentialRequest) => {
    setIsSubmitting(true);
    try {
      const created = await createCredential(data);
      setCredentials((prev) => [created, ...prev]);
      setShowAddForm(false);
      toast.success(`${PROVIDER_INFO[data.provider].label} credential added`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to add credential";
      if (errorMessage.includes("404") || errorMessage.toLowerCase().includes("not found")) {
        toast.error("Credentials API not available. Backend needs to implement /credentials endpoint.");
      } else {
        toast.error(errorMessage);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTest = async (id: string) => {
    const result = await testCredential(id);
    // Update local state with test result
    setCredentials((prev) =>
      prev.map((c) =>
        c.id === id
          ? {
              ...c,
              last_test_status: result.status,
              last_tested_at: result.tested_at,
              last_test_error: result.error ?? null,
            }
          : c
      )
    );
    if (result.status === "ok") {
      toast.success("Credential is valid");
    } else {
      toast.error("Credential test failed");
    }
    return result;
  };

  const handleRename = async (id: string, newName: string) => {
    try {
      const updated = await updateCredential(id, { name: newName });
      setCredentials((prev) => prev.map((c) => (c.id === id ? updated : c)));
      toast.success("Credential renamed");
    } catch (error) {
      toast.error("Failed to rename credential");
    }
  };

  const handleUpdateSecret = async (id: string, newSecret: string) => {
    try {
      const updated = await updateCredential(id, { secret: newSecret });
      setCredentials((prev) => prev.map((c) => (c.id === id ? { ...updated, last_test_status: "untested" as const } : c)));
      toast.success("API key updated");
    } catch (error) {
      toast.error("Failed to update API key");
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirmId) return;

    try {
      await deleteCredential(deleteConfirmId);
      setCredentials((prev) => prev.filter((c) => c.id !== deleteConfirmId));
      toast.success("Credential deleted");
    } catch (error) {
      toast.error("Failed to delete credential");
    } finally {
      setDeleteConfirmId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">
            {scope === "workspace" ? "Workspace" : "Project"} Credentials
          </h3>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            {scope === "workspace"
              ? "These credentials are available to all projects in this workspace."
              : "These credentials are specific to this project and override workspace credentials."}
          </p>
        </div>
        {!showAddForm && apiAvailable && (
          <button
            onClick={() => setShowAddForm(true)}
            className="btn-pill flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Credential
          </button>
        )}
      </div>

      {/* Add Form */}
      {showAddForm && (
        <div
          className="rounded-xl border p-4"
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderColor: "var(--border-default)",
          }}
        >
          <h4 className="text-sm font-medium text-white mb-4">Add New Credential</h4>
          <CredentialForm
            scope={scope}
            projectId={projectId}
            onSubmit={handleCreate}
            onCancel={() => setShowAddForm(false)}
            isSubmitting={isSubmitting}
          />
        </div>
      )}

      {/* Credentials List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <svg className="w-6 h-6 text-[var(--text-muted)] animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="ml-2 text-[var(--text-muted)]">Loading credentials...</span>
        </div>
      ) : credentials.length === 0 && !showAddForm ? (
        <div
          className="rounded-xl border border-dashed p-8 text-center"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div
            className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
            style={{ backgroundColor: "var(--bg-tertiary)" }}
          >
            <svg className="w-8 h-8 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          </div>
          {!apiAvailable ? (
            <>
              <h4 className="text-amber-400 font-medium mb-2">Credentials API Not Available</h4>
              <p className="text-sm text-[var(--text-muted)] mb-4">
                The backend credentials API is not implemented yet. For now, set your API keys as environment variables:
              </p>
              <div
                className="text-left text-xs font-mono p-3 rounded-lg mb-4"
                style={{ backgroundColor: "var(--bg-tertiary)" }}
              >
                <p className="text-[var(--text-secondary)]">OPENAI_API_KEY=sk-...</p>
                <p className="text-[var(--text-secondary)]">ANTHROPIC_API_KEY=sk-ant-...</p>
                <p className="text-[var(--text-secondary)]">GOOGLE_API_KEY=AIza...</p>
              </div>
            </>
          ) : (
            <>
              <h4 className="text-[var(--text-secondary)] font-medium mb-2">No credentials configured</h4>
              <p className="text-sm text-[var(--text-muted)] mb-4">
                Add API keys for OpenAI, Anthropic, or Google Gemini to run your flows.
              </p>
              <button onClick={() => setShowAddForm(true)} className="btn-pill">
                Add Your First Credential
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {credentials.map((credential) => (
            <CredentialCard
              key={credential.id}
              credential={credential}
              onTest={handleTest}
              onDelete={(id) => setDeleteConfirmId(id)}
              onRename={handleRename}
              onUpdateSecret={handleUpdateSecret}
            />
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
          <div
            className="rounded-xl p-6 max-w-md w-full mx-4"
            style={{
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border-default)",
            }}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">Delete Credential</h3>
                <p className="text-sm text-[var(--text-muted)]">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-[var(--text-secondary)] mb-6">
              Are you sure you want to delete this credential? Any flows using this credential will fail until a new one is configured.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
