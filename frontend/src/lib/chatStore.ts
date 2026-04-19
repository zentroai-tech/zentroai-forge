/**
 * Global Chat Store — manages chat state independently of the
 * ChatPlayground component lifecycle.
 *
 * Requests keep running even when the modal is closed. When the
 * user reopens the chat, the latest state (including responses that
 * arrived while the modal was closed) is shown immediately.
 */

import { create } from "zustand";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

interface FlowChat {
  messages: ChatMessage[];
  conversationId: string | null;
  isLoading: boolean;
}

interface ChatStore {
  /** Per-flow chat state. */
  chats: Record<string, FlowChat>;

  /** Get (or initialise) chat state for a flow. */
  getChat: (flowId: string) => FlowChat;

  /** Send a user message — runs the fetch in the store so it survives
   *  component unmounts. */
  sendMessage: (flowId: string, text: string) => void;

  /** Clear the conversation for a flow. */
  clearChat: (flowId: string) => void;
}

// ── localStorage helpers ─────────────────────────────────────────────

const STORAGE_PREFIX = "chat_playground_";

function loadChat(flowId: string): {
  messages: ChatMessage[];
  conversationId: string | null;
} {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${flowId}`);
    if (!raw) return { messages: [], conversationId: null };
    const data = JSON.parse(raw);
    return {
      messages: Array.isArray(data.messages) ? data.messages : [],
      conversationId: data.conversationId ?? null,
    };
  } catch {
    return { messages: [], conversationId: null };
  }
}

function persistChat(
  flowId: string,
  messages: ChatMessage[],
  conversationId: string | null,
) {
  try {
    localStorage.setItem(
      `${STORAGE_PREFIX}${flowId}`,
      JSON.stringify({ messages, conversationId }),
    );
  } catch {
    // quota exceeded — silently ignore
  }
}

function removeChat(flowId: string) {
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${flowId}`);
  } catch {
    // ignore
  }
}

// ── Default empty chat ───────────────────────────────────────────────

const emptyChat: FlowChat = {
  messages: [],
  conversationId: null,
  isLoading: false,
};

// ── Store ────────────────────────────────────────────────────────────

export const useChatStore = create<ChatStore>((set, get) => ({
  chats: {},

  getChat(flowId: string): FlowChat {
    const existing = get().chats[flowId];
    if (existing) return existing;

    // First access — hydrate from localStorage
    const saved = loadChat(flowId);
    const chat: FlowChat = {
      messages: saved.messages,
      conversationId: saved.conversationId,
      isLoading: false,
    };
    set((s) => ({ chats: { ...s.chats, [flowId]: chat } }));
    return chat;
  },

  sendMessage(flowId: string, text: string) {
    const chat = get().getChat(flowId);
    if (chat.isLoading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    // Optimistically add user message + set loading
    const updatedMessages = [...chat.messages, userMsg];
    set((s) => ({
      chats: {
        ...s.chats,
        [flowId]: {
          ...s.chats[flowId],
          messages: updatedMessages,
          isLoading: true,
        },
      },
    }));
    persistChat(flowId, updatedMessages, chat.conversationId);

    // Build history from existing messages (before the new user message)
    const history = chat.messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    // Fire the request — this runs in the module scope, NOT tied to React
    fetch(`${API_BASE}/flows/${flowId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        conversation_id: chat.conversationId,
        history,
      }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({
            detail: res.statusText,
          }));
          throw new Error(err.detail || "Request failed");
        }
        return res.json();
      })
      .then((data) => {
        const current = get().chats[flowId];
        if (!current) return; // chat was cleared while in-flight

        const convId = current.conversationId || data.conversation_id;
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: data.response,
          metadata: data.metadata,
          timestamp: new Date().toISOString(),
        };
        const newMessages = [...current.messages, assistantMsg];

        set((s) => ({
          chats: {
            ...s.chats,
            [flowId]: {
              messages: newMessages,
              conversationId: convId,
              isLoading: false,
            },
          },
        }));
        persistChat(flowId, newMessages, convId);
      })
      .catch((error) => {
        const current = get().chats[flowId];
        if (!current) return;

        const errorMsg: ChatMessage = {
          role: "assistant",
          content: `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
          timestamp: new Date().toISOString(),
        };
        const newMessages = [...current.messages, errorMsg];

        set((s) => ({
          chats: {
            ...s.chats,
            [flowId]: {
              ...current,
              messages: newMessages,
              isLoading: false,
            },
          },
        }));
        persistChat(flowId, newMessages, current.conversationId);
      });
  },

  clearChat(flowId: string) {
    set((s) => ({
      chats: {
        ...s.chats,
        [flowId]: { ...emptyChat },
      },
    }));
    removeChat(flowId);
  },
}));
