"use client";

import { useState } from "react";
import type { Credential, TestCredentialResponse } from "@/types/credentials";
import { PROVIDER_INFO } from "@/types/credentials";
import { formatDate } from "@/lib/utils";
import BrandIcon from "@/components/icons/BrandIcon";

interface CredentialCardProps {
  credential: Credential;
  onTest: (id: string) => Promise<TestCredentialResponse>;
  onDelete: (id: string) => void;
  onRename: (id: string, newName: string) => Promise<void>;
  onUpdateSecret: (id: string, newSecret: string) => Promise<void>;
}

export default function CredentialCard({
  credential,
  onTest,
  onDelete,
  onRename,
  onUpdateSecret,
}: CredentialCardProps) {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestCredentialResponse | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(credential.name ?? "");
  const [isUpdatingSecret, setIsUpdatingSecret] = useState(false);
  const [newSecret, setNewSecret] = useState("");
  const [showNewSecret, setShowNewSecret] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const providerInfo = PROVIDER_INFO[credential.provider];
  const brandName = credential.provider === "anthropic" ? "claude" : credential.provider;

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await onTest(credential.id);
      setTestResult(result);
    } catch (error) {
      setTestResult({
        id: credential.id,
        provider: credential.provider,
        status: "fail",
        error: error instanceof Error ? error.message : "Test failed",
        tested_at: new Date().toISOString(),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveName = async () => {
    if (editName.trim() === credential.name) {
      setIsEditing(false);
      return;
    }
    setIsSaving(true);
    try {
      await onRename(credential.id, editName.trim());
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveSecret = async () => {
    if (!newSecret.trim()) return;
    setIsSaving(true);
    try {
      await onUpdateSecret(credential.id, newSecret.trim());
      setIsUpdatingSecret(false);
      setNewSecret("");
    } finally {
      setIsSaving(false);
    }
  };

  const getStatusBadge = () => {
    const status = testResult?.status || credential.last_test_status;

    switch (status) {
      case "ok":
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
            Valid
          </span>
        );
      case "fail":
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-red-500/20 text-red-400 border border-red-500/30">
            Invalid
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--border-default)]">
            Untested
          </span>
        );
    }
  };

  return (
    <div
      className="rounded-xl border p-4"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      <div className="flex items-start justify-between">
        {/* Left: Provider info and name */}
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="w-7 h-7 rounded-md flex items-center justify-center bg-[var(--bg-tertiary)] border border-[var(--border-default)]">
            <BrandIcon name={brandName} size={18} alt={providerInfo.label} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-[var(--text-secondary)]">
                {providerInfo.label}
              </span>
              {getStatusBadge()}
            </div>

            {/* Name (editable) */}
            {isEditing ? (
              <div className="flex items-center gap-2 mt-1">
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="input-field py-1 px-2 text-sm flex-1"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName();
                    if (e.key === "Escape") {
                      setIsEditing(false);
                      setEditName(credential.name ?? "");
                    }
                  }}
                />
                <button
                  onClick={handleSaveName}
                  disabled={isSaving}
                  className="p-1 text-green-400 hover:text-green-300"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </button>
                <button
                  onClick={() => {
                    setIsEditing(false);
                    setEditName(credential.name ?? "");
                  }}
                  className="p-1 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="text-sm text-white hover:text-[var(--text-secondary)] mt-1 text-left"
              >
                {credential.name || "Unnamed credential"}
              </button>
            )}

            {/* Metadata */}
            <div className="flex items-center gap-3 mt-2 text-xs text-[var(--text-muted)]">
              <span>Created {formatDate(credential.created_at)}</span>
              {credential.last_tested_at && (
                <>
                  <span>|</span>
                  <span>Tested {formatDate(credential.last_tested_at)}</span>
                </>
              )}
            </div>

            {/* Test error message */}
            {(testResult?.error || credential.last_test_error) && (
              <p className="text-xs text-red-400 mt-2 truncate" title={testResult?.error || credential.last_test_error || undefined}>
                {(testResult?.error || credential.last_test_error || "").slice(0, 100)}
                {(testResult?.error || credential.last_test_error || "").length > 100 && "..."}
              </p>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleTest}
            disabled={isTesting}
            className="btn-secondary text-sm py-1.5 px-3"
            title="Test credential"
          >
            {isTesting ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              "Test"
            )}
          </button>
          <button
            onClick={() => setIsUpdatingSecret(true)}
            className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)] rounded"
            title="Update API key"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(credential.id)}
            className="p-1.5 text-[var(--text-muted)] hover:text-red-400 rounded"
            title="Delete credential"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>

      {/* Update Secret Form */}
      {isUpdatingSecret && (
        <div className="mt-4 pt-4 border-t border-[var(--border-default)]">
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
            New API Key
          </label>
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <input
                type={showNewSecret ? "text" : "password"}
                value={newSecret}
                onChange={(e) => setNewSecret(e.target.value)}
                placeholder={providerInfo.placeholder}
                className="input-field w-full pr-10"
                autoFocus
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowNewSecret(!showNewSecret)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                tabIndex={-1}
              >
                {showNewSecret ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                )}
              </button>
            </div>
            <button
              onClick={handleSaveSecret}
              disabled={isSaving || !newSecret.trim()}
              className="btn-pill py-2"
            >
              {isSaving ? "Saving..." : "Update"}
            </button>
            <button
              onClick={() => {
                setIsUpdatingSecret(false);
                setNewSecret("");
              }}
              className="btn-secondary py-2"
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-amber-400 mt-2">
            Warning: This will replace the existing API key. This action cannot be undone.
          </p>
        </div>
      )}
    </div>
  );
}
