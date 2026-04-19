"use client";

import { useEffect } from "react";

export interface GroupTab {
  id: string;
  label: string;
}

interface GroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  tabs: GroupTab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  title: string;
  children: React.ReactNode;
}

export default function GroupModal({
  isOpen,
  onClose,
  tabs,
  activeTab,
  onTabChange,
  title,
  children,
}: GroupModalProps) {
  // Escape key closes modal
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-6xl mx-4 h-[85vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Tab bar header */}
        <div
          className="flex items-center justify-between px-1 border-b flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center">
            <span
              className="text-xs font-medium px-3 py-3"
              style={{ color: "var(--text-muted)" }}
            >
              {title}
            </span>
            <div className="flex">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  className="relative px-4 py-3 text-sm font-medium transition-colors"
                  style={{
                    color:
                      activeTab === tab.id
                        ? "var(--text-primary)"
                        : "var(--text-muted)",
                  }}
                >
                  {tab.label}
                  {activeTab === tab.id && (
                    <span
                      className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                      style={{ backgroundColor: "var(--text-primary)" }}
                    />
                  )}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 mr-2 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
