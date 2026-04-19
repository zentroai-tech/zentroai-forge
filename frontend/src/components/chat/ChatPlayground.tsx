"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useChatStore } from "@/lib/chatStore";

interface ChatPlaygroundProps {
  flowId: string;
  onClose: () => void;
  embedded?: boolean;
}

export default function ChatPlayground({ flowId, onClose, embedded }: ChatPlaygroundProps) {
  // All state lives in the global store — survives unmounts
  const { getChat, sendMessage, clearChat } = useChatStore();
  const chat = useChatStore((s) => s.chats[flowId]) ?? getChat(flowId);

  const [input, setInput] = useState("");
  const [showMetadata, setShowMetadata] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chat.messages, chat.isLoading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || chat.isLoading) return;
    setInput("");
    sendMessage(flowId, text);
  }, [input, chat.isLoading, flowId, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    clearChat(flowId);
    setShowMetadata(null);
  };

  const embeddedToolbar = (
    <div className="px-4 py-2 border-b flex items-center gap-2 flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
      {chat.conversationId && (
        <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}>
          {chat.conversationId}
        </span>
      )}
      <div className="ml-auto">
        <button
          onClick={handleClear}
          disabled={chat.isLoading}
          className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)] disabled:opacity-40"
          style={{ color: "var(--text-muted)" }}
          title="Clear conversation"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>
    </div>
  );

  const messagesArea = (
    <>
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ backgroundColor: "var(--bg-primary)" }}>
          {chat.messages.length === 0 && !chat.isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)" }}
              >
                <svg className="w-8 h-8" style={{ color: "var(--text-muted)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                Test your agent conversationally
              </p>
              <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                Send a message to start. History is preserved across sessions.
              </p>
            </div>
          )}

          {chat.messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className="max-w-[85%]">
                <div
                  className={`rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === "user" ? "rounded-br-md" : "rounded-bl-md"
                  }`}
                  style={{
                    backgroundColor: msg.role === "user"
                      ? "var(--bg-tertiary)"
                      : "var(--bg-secondary)",
                    border: msg.role === "user"
                      ? "1px solid var(--border-hover)"
                      : "1px solid var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                >
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                </div>
                <div className="flex items-center gap-2 mt-1 px-1">
                  <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                  {msg.metadata && (
                    <button
                      onClick={() => setShowMetadata(showMetadata === idx ? null : idx)}
                      className="text-[10px] hover:underline"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {showMetadata === idx ? "hide info" : "show info"}
                    </button>
                  )}
                </div>
                {showMetadata === idx && msg.metadata && (
                  <div
                    className="mt-1 rounded-lg px-3 py-2 text-xs font-mono"
                    style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                  >
                    {msg.metadata.status ? <div>Status: {String(msg.metadata.status)}</div> : null}
                    {msg.metadata.duration_ms != null && <div>Duration: {Number(msg.metadata.duration_ms).toFixed(0)}ms</div>}
                    {msg.metadata.steps != null && <div>Steps: {String(msg.metadata.steps)}</div>}
                    {msg.metadata.models_used ? <div>Models: {(msg.metadata.models_used as string[]).join(", ")}</div> : null}
                    {msg.metadata.tokens_used != null && <div>Tokens: {String(msg.metadata.tokens_used)}</div>}
                  </div>
                )}
              </div>
            </div>
          ))}

          {chat.isLoading && (
            <div className="flex justify-start">
              <div
                className="rounded-2xl rounded-bl-md px-4 py-3 text-sm"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border-default)" }}
              >
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "0ms" }} />
                  <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "150ms" }} />
                  <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div
          className="p-4 border-t flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
              disabled={chat.isLoading}
              rows={1}
              className="flex-1 resize-none rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--border-active)]"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
                maxHeight: "120px",
              }}
              onInput={(e) => {
                const el = e.target as HTMLTextAreaElement;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 120) + "px";
              }}
            />
            <button
              onClick={handleSend}
              disabled={chat.isLoading || !input.trim()}
              className="self-end px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                color: input.trim() && !chat.isLoading ? "var(--text-primary)" : "var(--text-muted)",
                border: "1px solid " + (input.trim() && !chat.isLoading ? "var(--border-hover)" : "var(--border-default)"),
              }}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
    </>
  );

  if (embedded) return (
    <div className="h-full flex flex-col">
      {embeddedToolbar}
      {messagesArea}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-2xl mx-4 h-[80vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Chat Playground</h2>
            {chat.conversationId && (
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}>
                {chat.conversationId}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              disabled={chat.isLoading}
              className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)] disabled:opacity-40"
              style={{ color: "var(--text-muted)" }}
              title="Clear conversation"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
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
        </div>

        {messagesArea}
      </div>
    </div>
  );
}
