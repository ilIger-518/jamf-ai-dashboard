"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LogOut,
  User,
  Server,
  ArrowUpCircle,
  Bell,
  AlertTriangle,
  Info,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { api } from "@/lib/api";

interface JamfServer { id: string; name: string; }
interface UpdateStatus { update_available: boolean; latest_commit: string; }
interface DashboardLogEntry {
  id: string;
  category: "server" | "login" | "action";
  level: string;
  message: string;
  status_code: number | null;
  created_at: string;
}

interface NotificationItem {
  id: string;
  tone: "warning" | "error" | "info" | "success";
  title: string;
  detail: string;
  createdAt: string;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "unknown time";
  return date.toLocaleString();
}

export function TopNav() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { selectedServerId } = useUiStore();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const canViewLogs = Boolean(user?.is_admin || user?.permissions?.includes("settings.manage"));

  const { data: servers = [] } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
    staleTime: 60_000,
  });

  const { data: updateStatus } = useQuery<UpdateStatus>({
    queryKey: ["system", "update-status"],
    queryFn: () =>
      api.get<UpdateStatus>("/system/update/status").then((r) => r.data),
    enabled: !!user?.is_admin,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: true,
    retry: false,
  });

  const { data: recentLogs = [] } = useQuery<DashboardLogEntry[]>({
    queryKey: ["topnav", "notifications", "logs"],
    queryFn: () =>
      api
        .get<DashboardLogEntry[]>("/logs", {
          params: { limit: 25 },
        })
        .then((r) => r.data),
    enabled: canViewLogs,
    staleTime: 45_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    retry: false,
  });

  useEffect(() => {
    if (!menuOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!menuRef.current?.contains(target)) {
        setMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

  const notifications = useMemo<NotificationItem[]>(() => {
    const items: NotificationItem[] = [];

    if (user?.is_admin && updateStatus?.update_available) {
      items.push({
        id: "update-available",
        tone: "warning",
        title: "Update available",
        detail: updateStatus.latest_commit,
        createdAt: new Date().toISOString(),
      });
    }

    for (const log of recentLogs) {
      const level = log.level.toLowerCase();
      const isError = level.includes("error") || (typeof log.status_code === "number" && log.status_code >= 500);
      const isWarning = level.includes("warn") || (typeof log.status_code === "number" && log.status_code >= 400);
      if (!isError && !isWarning) continue;

      items.push({
        id: `log-${log.id}`,
        tone: isError ? "error" : "warning",
        title: log.message,
        detail: `${log.category.toUpperCase()}${log.status_code ? ` • ${log.status_code}` : ""}`,
        createdAt: log.created_at,
      });

      if (items.length >= 8) break;
    }

    if (items.length === 0) {
      items.push({
        id: "all-clear",
        tone: "success",
        title: "All clear",
        detail: "No active alerts right now.",
        createdAt: new Date().toISOString(),
      });
    }

    return items;
  }, [recentLogs, updateStatus, user?.is_admin]);

  const unreadCount = notifications[0]?.id === "all-clear" ? 0 : notifications.length;

  const selectedName = selectedServerId
    ? (servers.find((s) => s.id === selectedServerId)?.name ?? null)
    : null;

  const handleLogout = async () => {
    await logout();
    toast.success("Signed out");
    router.replace("/login");
  };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-2">
        {selectedName ? (
          <span className="flex items-center gap-1.5 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300">
            <Server className="h-3 w-3" />
            {selectedName}
          </span>
        ) : (
          <span className="text-xs text-gray-400 dark:text-gray-500">All Servers</span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="relative rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition"
            aria-label="Open notifications"
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 inline-flex min-h-4 min-w-4 items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-semibold leading-none text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {menuOpen && (
            <div className="absolute right-0 z-30 mt-2 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900">
              <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 dark:border-gray-800">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Notifications</p>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    router.push("/settings");
                  }}
                  className="text-xs font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300"
                >
                  View all
                </button>
              </div>
              <ul className="max-h-80 overflow-y-auto py-1">
                {notifications.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        if (item.id !== "all-clear") {
                          router.push("/settings");
                        }
                      }}
                      className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800/70 transition"
                    >
                      {item.tone === "error" && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />}
                      {item.tone === "warning" && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />}
                      {item.tone === "info" && <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />}
                      {item.tone === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />}
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-gray-900 dark:text-gray-100">{item.title}</span>
                        <span className="block truncate text-xs text-gray-500 dark:text-gray-400">{item.detail}</span>
                        <span className="block text-[11px] text-gray-400 dark:text-gray-500">{formatTime(item.createdAt)}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {user?.is_admin && updateStatus?.update_available && (
          <button
            onClick={() => router.push("/settings")}
            title={`Update available: ${updateStatus.latest_commit}`}
            className="flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700 hover:bg-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:hover:bg-amber-900/60 transition"
          >
            <ArrowUpCircle className="h-3.5 w-3.5" />
            Update available
          </button>
        )}
        {user && (
          <span className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400">
            <User className="h-4 w-4" />
            {user.username}
            {user.role_name && (
              <span className="ml-1 rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700 dark:bg-green-950 dark:text-green-300">
                {user.role_name}
              </span>
            )}
          </span>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </header>
  );
}
