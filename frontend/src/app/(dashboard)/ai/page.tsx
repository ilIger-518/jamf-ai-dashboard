"use client";

import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Send,
  User,
  BookOpen,
  Plus,
  MessageSquare,
  Trash2,
  PenLine,
  ShieldCheck,
  Wrench,
  Square,
  Check,
  X,
} from "lucide-react";
import { api, API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface JamfServer {
  id: string;
  name: string;
  is_active: boolean;
}

interface KnowledgeBase {
  id: string;
  name: string;
  dimension_tag: string | null;
  is_default: boolean;
}

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

async function extractErrorMessage(response: Response): Promise<string> {
  const fallback = "Could not reach the AI service. Make sure Ollama is running.";
  const contentType = response.headers.get("content-type") || "";

  try {
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown; title?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
      if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
      if (typeof payload.title === "string" && payload.title.trim()) return payload.title;
    } else {
      const text = (await response.text()).trim();
      if (text) return text;
    }
  } catch {
    // Fall back to the generic message below.
  }

  return fallback;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AiAssistantPage() {
  const qc = useQueryClient();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [botMode, setBotMode] = useState<"rag_readonly" | "policy_builder">("rag_readonly");
  const [targetServerId, setTargetServerId] = useState<string>("");
  const [selectedKnowledgeBaseIds, setSelectedKnowledgeBaseIds] = useState<string[]>([]);
  const [draggingKnowledgeBaseId, setDraggingKnowledgeBaseId] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingText, setThinkingText] = useState("Idle");
  const [streamReply, setStreamReply] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages]);

  // Focus input when session changes
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  // ---- Fetch sessions list ----
  const { data: sessions = [] } = useQuery<Session[]>({
    queryKey: ["ai-sessions"],
    queryFn: () => api.get<Session[]>("/ai/sessions").then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: servers = [] } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
    staleTime: 60_000,
  });

  const { data: knowledgeBases = [] } = useQuery<KnowledgeBase[]>({
    queryKey: ["knowledge-bases"],
    queryFn: () => api.get<KnowledgeBase[]>("/knowledge/bases").then((r) => r.data),
  });

  useEffect(() => {
    if (knowledgeBases.length === 0) return;
    if (selectedKnowledgeBaseIds.length > 0) {
      const existing = new Set(knowledgeBases.map((kb) => kb.id));
      const filtered = selectedKnowledgeBaseIds.filter((id) => existing.has(id));
      if (filtered.length !== selectedKnowledgeBaseIds.length) {
        setSelectedKnowledgeBaseIds(filtered);
      }
      return;
    }
    setSelectedKnowledgeBaseIds(knowledgeBases.map((kb) => kb.id));
  }, [knowledgeBases, selectedKnowledgeBaseIds]);

  useEffect(() => {
    if (!targetServerId && servers.length > 0) {
      const firstActive = servers.find((s) => s.is_active) ?? servers[0];
      setTargetServerId(firstActive.id);
    }
  }, [servers, targetServerId]);

  // ---- Fetch messages for active session ----
  const { data: sessionMessages = [] } = useQuery<Message[]>({
    queryKey: ["ai-messages", activeSessionId],
    queryFn: () =>
      api
        .get<Message[]>(`/ai/sessions/${activeSessionId}/messages`)
        .then((r) => r.data),
    enabled: !!activeSessionId,
  });

  // Sync fetched messages to local state when switching sessions
  useEffect(() => {
    if (activeSessionId) {
      setLocalMessages(
        sessionMessages.map((m) => ({
          ...m,
          sources: m.sources ?? [],
        }))
      );
    } else {
      setLocalMessages([]);
    }
  }, [activeSessionId, sessionMessages]);

  // ---- Send message (streaming) ----
  const sendStreamMessage = async (message: string, signal: AbortSignal) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/ai/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({
        message,
        session_id: activeSessionId,
        bot_mode: botMode,
        target_server_id: botMode === "policy_builder" ? targetServerId || null : null,
        knowledge_base_ids: botMode === "rag_readonly" ? selectedKnowledgeBaseIds : null,
      }),
      signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(await extractErrorMessage(response));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalPayload: { session_id: string; reply: string; sources: string[] } | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const event = JSON.parse(trimmed) as {
          type: "stage" | "delta" | "final" | "error";
          message?: string;
          content?: string;
          session_id?: string;
          reply?: string;
          sources?: string[];
        };

        if (event.type === "stage") {
          setThinkingText(event.message ?? "Thinking...");
          continue;
        }
        if (event.type === "delta") {
          if (event.content) {
            setStreamReply((prev) => prev + event.content);
          }
          continue;
        }
        if (event.type === "error") {
          throw new Error(event.message || "Unexpected error calling the AI service.");
        }
        if (event.type === "final" && event.session_id && typeof event.reply === "string") {
          finalPayload = {
            session_id: event.session_id,
            reply: event.reply,
            sources: event.sources ?? [],
          };
        }
      }
    }

    if (!finalPayload) {
      throw new Error("AI stream ended without a final response.");
    }
    return finalPayload;
  };

  const sendText = (text: string) => {
    if (!text.trim() || isThinking) return;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsThinking(true);
    setThinkingText("Starting...");
    setStreamReply("");
    setLocalMessages((m) => [...m, { role: "user", content: text }]);
    void sendStreamMessage(text, controller.signal)
      .then((data) => {
        if (!activeSessionId || activeSessionId !== data.session_id) {
          setActiveSessionId(data.session_id);
        }
        setLocalMessages((m) => [
          ...m,
          { role: "assistant", content: data.reply, sources: data.sources },
        ]);
        qc.invalidateQueries({ queryKey: ["ai-sessions"] });
        qc.invalidateQueries({ queryKey: ["ai-messages", data.session_id] });
      })
      .catch((err: unknown) => {
        const canceled =
          (err as { name?: string })?.name === "AbortError" ||
          (err as { code?: string; name?: string })?.code === "ERR_CANCELED";
        if (!canceled) {
          const detail = err instanceof Error ? err.message : "Unexpected error calling the AI service.";
          setLocalMessages((m) => [...m, { role: "assistant", content: detail }]);
        }
      })
      .finally(() => {
        abortControllerRef.current = null;
        setIsThinking(false);
        setStreamReply("");
      });
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput("");
    sendText(text);
  };

  const handleStop = () => {
    if (!isThinking) return;
    abortControllerRef.current?.abort();
    setLocalMessages((m) => [...m, { role: "assistant", content: "Stopped." }]);
    setIsThinking(false);
    setThinkingText("Stopped");
    setStreamReply("");
  };

  // ---- New chat ----
  const startNewChat = () => {
    setActiveSessionId(null);
    setLocalMessages([]);
    setInput("");
    inputRef.current?.focus();
  };

  // ---- Delete session ----
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/ai/sessions/${id}`),
    onSuccess: (_data, id) => {
      if (activeSessionId === id) startNewChat();
      qc.invalidateQueries({ queryKey: ["ai-sessions"] });
      toast.success("Chat deleted");
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Failed to delete chat";
      toast.error(detail);
    },
  });

  // ---- Rename session (optimistic local-only, persisting to title via first-message auto-title) ----
  const confirmRename = async () => {
    if (!renaming || !renameValue.trim()) { setRenaming(null); return; }
    // Update locally immediately
    qc.setQueryData<Session[]>(["ai-sessions"], (old = []) =>
      old.map((s) => (s.id === renaming ? { ...s, title: renameValue.trim() } : s))
    );
    setRenaming(null);
  };

  const displayMessages = activeSessionId ? localMessages : localMessages;
  const orderedSelectedKnowledgeBases = selectedKnowledgeBaseIds
    .map((id) => knowledgeBases.find((kb) => kb.id === id))
    .filter((kb): kb is KnowledgeBase => !!kb);
  const unselectedKnowledgeBases = knowledgeBases.filter(
    (kb) => !selectedKnowledgeBaseIds.includes(kb.id),
  );
  const orderedKnowledgeBases = [...orderedSelectedKnowledgeBases, ...unselectedKnowledgeBases];

  const toggleKnowledgeBase = (kbId: string) => {
    setSelectedKnowledgeBaseIds((prev) => {
      if (prev.includes(kbId)) {
        if (prev.length <= 1) return prev;
        return prev.filter((id) => id !== kbId);
      }
      return [...prev, kbId];
    });
  };

  const moveKnowledgeBase = (dragId: string, targetId: string) => {
    if (dragId === targetId) return;
    setSelectedKnowledgeBaseIds((prev) => {
      const next = [...prev];
      const from = next.indexOf(dragId);
      const to = next.indexOf(targetId);
      if (from < 0 || to < 0) return prev;
      next.splice(from, 1);
      next.splice(to, 0, dragId);
      return next;
    });
  };

  const lastAssistantMessage = [...displayMessages].reverse().find((m) => m.role === "assistant");
  const hasPendingApproval =
    botMode === "policy_builder" &&
    !!lastAssistantMessage?.content &&
    lastAssistantMessage.content.includes("API command preview") &&
    lastAssistantMessage.content.includes("Reply with `approve` to execute or `cancel` to discard.");

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* ---------------------------------------------------------------- */}
      {/* Sidebar                                                           */}
      {/* ---------------------------------------------------------------- */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900">
        {/* New chat button */}
        <div className="p-3">
          <button
            onClick={startNewChat}
            className="flex w-full items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            <Plus className="h-4 w-4" />
            New chat
          </button>
        </div>

        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {sessions.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-gray-400 dark:text-gray-500">
              No chats yet
            </p>
          ) : (
            <ul className="space-y-0.5">
              {sessions.map((s) => (
                <li key={s.id}>
                  {renaming === s.id ? (
                    <div className="flex items-center gap-1 rounded-lg bg-blue-50 px-2 py-1.5 dark:bg-blue-950">
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") confirmRename();
                          if (e.key === "Escape") setRenaming(null);
                        }}
                        onBlur={confirmRename}
                        className="min-w-0 flex-1 rounded bg-white px-1 py-0.5 text-xs text-gray-900 outline-none dark:bg-gray-800 dark:text-white"
                      />
                    </div>
                  ) : (
                    <div
                      className={cn(
                        "group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm",
                        activeSessionId === s.id
                          ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200"
                          : "text-gray-700 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-700/60"
                      )}
                      onClick={() => setActiveSessionId(s.id)}
                    >
                      <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium leading-tight">
                          {s.title || "New Chat"}
                        </p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500">
                          {relativeTime(s.updated_at)}
                        </p>
                      </div>
                      {/* Action buttons — visible on hover */}
                      <div className="hidden shrink-0 items-center gap-0.5 group-hover:flex">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenaming(s.id);
                            setRenameValue(s.title || "");
                          }}
                          className="rounded p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                          title="Rename"
                        >
                          <PenLine className="h-3 w-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm("Delete this chat?")) deleteMutation.mutate(s.id);
                          }}
                          className="rounded p-0.5 text-gray-400 hover:text-red-500"
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* ---------------------------------------------------------------- */}
      {/* Main chat area                                                    */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="flex flex-wrap items-center gap-3 border-b border-gray-200 px-6 py-3 dark:border-gray-700">
          <Bot className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          <h1 className="text-base font-semibold text-gray-900 dark:text-white">
            {activeSessionId
              ? (sessions.find((s) => s.id === activeSessionId)?.title || "Chat")
              : "AI Assistant"}
          </h1>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                if (botMode !== "rag_readonly") startNewChat();
                setBotMode("rag_readonly");
              }}
              className={cn(
                "inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-medium",
                botMode === "rag_readonly"
                  ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-900/30 dark:text-blue-300"
                  : "border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800",
              )}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              RAG Read-Only
            </button>

            <button
              onClick={() => {
                if (botMode !== "policy_builder") startNewChat();
                setBotMode("policy_builder");
              }}
              className={cn(
                "inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-medium",
                botMode === "policy_builder"
                  ? "border-amber-500 bg-amber-50 text-amber-700 dark:border-amber-500 dark:bg-amber-900/30 dark:text-amber-300"
                  : "border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800",
              )}
            >
              <Wrench className="h-3.5 w-3.5" />
              Policy & Group Builder
            </button>

            {botMode === "policy_builder" && (
              <select
                value={targetServerId}
                onChange={(e) => setTargetServerId(e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              >
                {servers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name}{server.is_active ? "" : " (inactive)"}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {botMode === "rag_readonly" && knowledgeBases.length > 0 && (
          <div className="border-b border-gray-200 bg-gray-50 px-6 py-3 dark:border-gray-700 dark:bg-gray-900/50">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Knowledge Bases (drag to set priority)
            </p>
            <div className="grid gap-1.5 md:grid-cols-2">
              {orderedKnowledgeBases.map((kb, index) => (
                <label
                  key={kb.id}
                  draggable={selectedKnowledgeBaseIds.includes(kb.id)}
                  onDragStart={() => {
                    if (!selectedKnowledgeBaseIds.includes(kb.id)) return;
                    setDraggingKnowledgeBaseId(kb.id);
                  }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (!draggingKnowledgeBaseId) return;
                    if (!selectedKnowledgeBaseIds.includes(kb.id)) return;
                    moveKnowledgeBase(draggingKnowledgeBaseId, kb.id);
                    setDraggingKnowledgeBaseId(null);
                  }}
                  className={cn(
                    "flex cursor-move items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs dark:border-gray-600 dark:bg-gray-800",
                    draggingKnowledgeBaseId === kb.id && "opacity-60",
                    !selectedKnowledgeBaseIds.includes(kb.id) && "cursor-default opacity-75",
                  )}
                >
                  <span className="w-4 text-[10px] font-semibold text-gray-500 dark:text-gray-400">
                    {selectedKnowledgeBaseIds.includes(kb.id) ? index + 1 : "-"}
                  </span>
                  <input
                    type="checkbox"
                    checked={selectedKnowledgeBaseIds.includes(kb.id)}
                    onChange={() => toggleKnowledgeBase(kb.id)}
                    className="h-3.5 w-3.5 rounded accent-blue-600"
                  />
                  <span className="truncate font-medium text-gray-700 dark:text-gray-200">{kb.name}</span>
                  {kb.dimension_tag && (
                    <span className="ml-auto rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                      {kb.dimension_tag}
                    </span>
                  )}
                </label>
              ))}
            </div>
            <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
              Priority flows top to bottom. Highest priority knowledge base is queried first.
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {displayMessages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <div className="rounded-xl bg-blue-50 p-4 dark:bg-blue-950">
                <Bot className="h-10 w-10 text-blue-600 dark:text-blue-400" />
              </div>
              <p className="text-base font-medium text-gray-700 dark:text-gray-300">
                {botMode === "policy_builder" ? "Jamf Policy & Group Builder" : "Jamf AI Assistant"}
              </p>
              <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">
                {botMode === "policy_builder"
                  ? "Ask for policy or group drafts, or request creation on the selected Jamf server."
                  : "Ask questions about your devices, policies, patch status, or compliance. Powered by your local Ollama instance."}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-left text-xs">
                {(botMode === "policy_builder"
                  ? [
                      "Create a policy to install Zoom at startup",
                      "Create a static group for all marketing laptops",
                      "Create a smart group for computers with names containing LAB",
                      "Draft a policy for FileVault compliance reminder",
                    ]
                  : [
                      "How many unmanaged devices do I have?",
                      "What policies are enabled?",
                      "Show me patch compliance status",
                      "Any smart groups configured?",
                    ]).map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      inputRef.current?.focus();
                    }}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-gray-600 hover:border-blue-300 hover:bg-blue-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {displayMessages.map((msg, i) => (
                <div
                  key={msg.id ?? i}
                  className={cn(
                    "flex gap-3",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-950">
                      <Bot className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm",
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-white"
                    )}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-700">
                        <p className="mb-1 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                          <BookOpen className="h-3 w-3" /> Sources
                        </p>
                        {msg.sources.map((s) => (
                          <a
                            key={s}
                            href={s}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="block truncate text-xs text-blue-600 hover:underline dark:text-blue-400"
                          >
                            {s.replace(/^https?:\/\//, "")}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-200 dark:bg-gray-700">
                      <User className="h-4 w-4 text-gray-600 dark:text-gray-300" />
                    </div>
                  )}
                </div>
              ))}
              {isThinking && (
                <div className="flex gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-950">
                    <Bot className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="rounded-2xl bg-gray-100 px-4 py-2.5 text-sm text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    {streamReply ? (
                      <p className="whitespace-pre-wrap text-gray-700 dark:text-gray-200">{streamReply}</p>
                    ) : (
                      <span className="inline-flex gap-1">
                        <span className="animate-bounce">●</span>
                        <span className="animate-bounce [animation-delay:0.1s]">●</span>
                        <span className="animate-bounce [animation-delay:0.2s]">●</span>
                      </span>
                    )}
                    <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{thinkingText}</p>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="border-t border-gray-200 px-6 py-4 dark:border-gray-700">
          {isThinking && (
            <div className="mx-auto mb-1 max-w-3xl text-[11px] text-gray-500 dark:text-gray-400">
              AI thinking: {thinkingText}
            </div>
          )}
          {hasPendingApproval && !isThinking && (
            <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2 text-[11px]">
              <button
                onClick={() => sendText("approve")}
                className="inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
              >
                <Check className="h-3 w-3" />
                Approve
              </button>
              <button
                onClick={() => sendText("cancel")}
                className="inline-flex items-center gap-1 rounded-md border border-rose-300 bg-rose-50 px-2 py-1 text-rose-700 hover:bg-rose-100 dark:border-rose-700 dark:bg-rose-900/30 dark:text-rose-300"
              >
                <X className="h-3 w-3" />
                Cancel
              </button>
              <span className="text-gray-500 dark:text-gray-400">Pending action preview detected.</span>
            </div>
          )}
          <div className="mx-auto flex max-w-3xl gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={
                botMode === "policy_builder"
                  ? "Ask Policy & Group Builder to draft or create a Jamf policy or computer group…"
                  : "Ask about your Jamf environment…"
              }
              disabled={isThinking}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
            <button
              onClick={isThinking ? handleStop : handleSend}
              disabled={!isThinking && !input.trim()}
              className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isThinking ? <Square className="h-4 w-4" /> : <Send className="h-4 w-4" />}
              {isThinking ? "Stop" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
