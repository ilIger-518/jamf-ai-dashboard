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
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
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
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  // ---- Send message ----
  const sendMutation = useMutation({
    mutationFn: (message: string) =>
      api
        .post<{ session_id: string; reply: string; sources: string[] }>("/ai/chat", {
          message,
          session_id: activeSessionId,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      // If this was a new session, switch to it
      if (!activeSessionId || activeSessionId !== data.session_id) {
        setActiveSessionId(data.session_id);
      }
      setLocalMessages((m) => [
        ...m,
        { role: "assistant", content: data.reply, sources: data.sources },
      ]);
      // Refresh sessions list (title & updated_at changed)
      qc.invalidateQueries({ queryKey: ["ai-sessions"] });
      qc.invalidateQueries({ queryKey: ["ai-messages", data.session_id] });
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ??
        "Could not reach the AI service. Make sure Ollama is running.";
      setLocalMessages((m) => [...m, { role: "assistant", content: detail }]);
    },
  });

  const handleSend = () => {
    const text = input.trim();
    if (!text || sendMutation.isPending) return;
    setInput("");
    setLocalMessages((m) => [...m, { role: "user", content: text }]);
    sendMutation.mutate(text);
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
        <div className="flex items-center border-b border-gray-200 px-6 py-3 dark:border-gray-700">
          <Bot className="mr-2 h-5 w-5 text-blue-600 dark:text-blue-400" />
          <h1 className="text-base font-semibold text-gray-900 dark:text-white">
            {activeSessionId
              ? (sessions.find((s) => s.id === activeSessionId)?.title || "Chat")
              : "AI Assistant"}
          </h1>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {displayMessages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <div className="rounded-xl bg-blue-50 p-4 dark:bg-blue-950">
                <Bot className="h-10 w-10 text-blue-600 dark:text-blue-400" />
              </div>
              <p className="text-base font-medium text-gray-700 dark:text-gray-300">
                Jamf AI Assistant
              </p>
              <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">
                Ask questions about your devices, policies, patch status, or
                compliance. Powered by your local Ollama instance.
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-left text-xs">
                {[
                  "How many unmanaged devices do I have?",
                  "What policies are enabled?",
                  "Show me patch compliance status",
                  "Any smart groups configured?",
                ].map((q) => (
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
              {sendMutation.isPending && (
                <div className="flex gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-950">
                    <Bot className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="rounded-2xl bg-gray-100 px-4 py-2.5 text-sm text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    <span className="inline-flex gap-1">
                      <span className="animate-bounce">●</span>
                      <span className="animate-bounce [animation-delay:0.1s]">●</span>
                      <span className="animate-bounce [animation-delay:0.2s]">●</span>
                    </span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="border-t border-gray-200 px-6 py-4 dark:border-gray-700">
          <div className="mx-auto flex max-w-3xl gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="Ask about your Jamf environment…"
              disabled={sendMutation.isPending}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sendMutation.isPending}
              className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

