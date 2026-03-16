"use client";

import { LogOut, User, Server, ArrowUpCircle } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { api } from "@/lib/api";

interface JamfServer { id: string; name: string; }
interface UpdateStatus { update_available: boolean; latest_commit: string; }

export function TopNav() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { selectedServerId } = useUiStore();

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
    retry: false,
  });

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
