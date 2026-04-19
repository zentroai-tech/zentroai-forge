"use client";

import { useState } from "react";
import type {
  CredentialProvider,
  CredentialScopeType,
  CreateCredentialRequest,
} from "@/types/credentials";
import { PROVIDER_INFO } from "@/types/credentials";
import BrandIcon from "@/components/icons/BrandIcon";

interface CredentialFormProps {
  scope: CredentialScopeType;
  projectId?: string;
  onSubmit: (data: CreateCredentialRequest) => Promise<void>;
  onCancel: () => void;
  isSubmitting?: boolean;
}

export default function CredentialForm({
  scope,
  projectId,
  onSubmit,
  onCancel,
  isSubmitting = false,
}: CredentialFormProps) {
  const [provider, setProvider] = useState<CredentialProvider | "">("");
  const [secret, setSecret] = useState("");
  const [name, setName] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [errors, setErrors] = useState<{ provider?: string; secret?: string }>({});

  const validate = (): boolean => {
    const newErrors: { provider?: string; secret?: string } = {};

    if (!provider) {
      newErrors.provider = "Please select a provider";
    }
    if (!secret.trim()) {
      newErrors.secret = "API key is required";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate() || !provider) return;

    await onSubmit({
      provider,
      secret: secret.trim(),
      name: name.trim() || undefined,
      scope_type: scope,
      scope_id: projectId || "default",
    });

    // Clear form after successful submission
    setProvider("");
    setSecret("");
    setName("");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Provider Selection */}
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
          Provider
        </label>
        <div className="grid grid-cols-3 gap-2">
          {(Object.keys(PROVIDER_INFO) as CredentialProvider[]).map((p) => {
            const info = PROVIDER_INFO[p];
            const isSelected = provider === p;
            const brandName = p === "anthropic" ? "claude" : p;

            return (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setProvider(p);
                  if (errors.provider) setErrors((prev) => ({ ...prev, provider: undefined }));
                }}
                className={`p-3 rounded-lg border-2 transition-all text-left ${
                  isSelected
                    ? "border-cyan-500 bg-cyan-500/10"
                    : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                }`}
                disabled={isSubmitting}
              >
                <div className="flex items-center gap-2">
                  <BrandIcon name={brandName} size={16} alt={info.label} />
                  <span className={`text-sm font-medium ${isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                    {info.label}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
        {errors.provider && (
          <p className="text-xs text-red-400 mt-1">{errors.provider}</p>
        )}
      </div>

      {/* Name (optional) */}
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
          Name <span className="text-[var(--text-muted)]">(optional)</span>
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., Production Key, Dev Key"
          className="input-field w-full"
          disabled={isSubmitting}
        />
      </div>

      {/* API Key */}
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
          API Key
        </label>
        <div className="relative">
          <input
            type={showSecret ? "text" : "password"}
            value={secret}
            onChange={(e) => {
              setSecret(e.target.value);
              if (errors.secret) setErrors((prev) => ({ ...prev, secret: undefined }));
            }}
            placeholder={provider ? PROVIDER_INFO[provider].placeholder : "Enter your API key"}
            className={`input-field w-full pr-10 ${errors.secret ? "border-red-500" : ""}`}
            disabled={isSubmitting}
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => setShowSecret(!showSecret)}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            tabIndex={-1}
          >
            {showSecret ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            )}
          </button>
        </div>
        {errors.secret && (
          <p className="text-xs text-red-400 mt-1">{errors.secret}</p>
        )}
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Your API key is encrypted and stored securely. It will not be displayed after saving.
        </p>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary"
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn-pill"
          disabled={isSubmitting || !provider || !secret.trim()}
        >
          {isSubmitting ? (
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Saving...
            </span>
          ) : (
            "Save Credential"
          )}
        </button>
      </div>
    </form>
  );
}
