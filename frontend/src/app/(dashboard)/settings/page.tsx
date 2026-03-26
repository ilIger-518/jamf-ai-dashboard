"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Pencil,
  Server,
  Wand2,
  ShieldCheck,
  ShieldAlert,
  ChevronRight,
  Loader2,
  RotateCw,
  Users,
  KeyRound,
  ScrollText,
  ArrowUpCircle,
  CheckCheck,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

interface JamfServer {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
  last_sync: string | null;
  last_sync_error: string | null;
  created_at: string;
}

interface ServerFormValues {
  name: string;
  url: string;
  client_id: string;
  client_secret: string;
  ai_client_id: string;
  ai_client_secret: string;
}

interface AppRole {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

interface ManagedUser {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  role: AppRole | null;
  permissions: string[];
}

interface PermissionOption {
  key: string;
  label: string;
}

interface DashboardLogEntry {
  id: string;
  category: "server" | "login" | "action";
  action: string;
  level: string;
  message: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  username: string | null;
  ip_address: string | null;
  created_at: string;
}

interface DockerLogsData {
  service: string | null;
  tail: number;
  services: string[];
  logs: string;
}

function getErrorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown; title?: unknown } } })?.response?.data;
  if (typeof detail?.detail === "string" && detail.detail.trim()) return detail.detail;
  if (typeof detail?.title === "string" && detail.title.trim()) return detail.title;
  const message = (error as { message?: unknown })?.message;
  if (typeof message === "string" && message.trim()) return message;
  return fallback;
}

const LEVEL_COLORS: Record<string, string> = {
  info: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  warning: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

const CATEGORY_COLORS: Record<string, string> = {
  server: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  login: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  action: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
};

interface UpdateStatusData {
  current_commit: string;
  latest_commit: string;
  current_version: string | null;
  latest_version: string | null;
  repo_url: string;
  branch: string;
  commit_graph: {
    sha: string;
    message: string;
    author: string;
    date: string | null;
    is_current: boolean;
    is_latest: boolean;
    is_behind_path: boolean;
  }[];
  update_available: boolean;
  last_checked: string | null;
  update_in_progress: boolean;
  last_update_result: string | null;
  last_update_at: string | null;
  log: string[];
}

function UpdatesPanel() {
  const qc = useQueryClient();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [isConfigDirty, setIsConfigDirty] = useState(false);

  const { data: status, isLoading, error } = useQuery<UpdateStatusData>({
    queryKey: ["system", "update-status"],
    queryFn: () => api.get<UpdateStatusData>("/system/update/status").then((r) => r.data),
    refetchInterval: 10_000,
    retry: false,
  });

  const checkMutation = useMutation({
    mutationFn: () => api.post("/system/update/check").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["system", "update-status"] }),
    onError: () => toast.error("Check failed — updater may be unavailable"),
  });

  const saveConfigMutation = useMutation({
    mutationFn: () =>
      api
        .post("/system/update/config", {
          repo_url: repoUrl.trim(),
          branch: branch.trim() || "main",
        })
        .then((r) => r.data),
    onSuccess: () => {
      setIsConfigDirty(false);
      toast.success("Update source saved");
      qc.invalidateQueries({ queryKey: ["system", "update-status"] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to save update source");
    },
  });

  const applyMutation = useMutation({
    mutationFn: () => api.post("/system/update/apply").then((r) => r.data),
    onSuccess: (data: { ok: boolean; message: string }) => {
      if (data.ok) toast.success(data.message);
      else toast.error(data.message);
      qc.invalidateQueries({ queryKey: ["system", "update-status"] });
    },
    onError: () => toast.error("Apply failed — updater may be unavailable"),
  });

  useEffect(() => {
    if (!status || isConfigDirty) return;
    setRepoUrl(status.repo_url || "");
    setBranch(status.branch || "main");
  }, [status, isConfigDirty]);

  if (error) {
    const errorStatus = (error as { response?: { status?: number } })?.response?.status;
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
        {errorStatus === 401 || errorStatus === 403 ? (
          <>
            <p className="font-medium">Insufficient permissions</p>
            <p className="mt-1 text-xs opacity-80">Only admin users can query updater status and apply updates.</p>
          </>
        ) : (
          <>
            <p className="font-medium">Updater service unavailable</p>
            <p className="mt-1 text-xs opacity-80">Start the updater container or check docker compose logs.</p>
          </>
        )}
      </div>
    );
  }

  const resultBadge = status?.last_update_result;
  const commitBaseUrl = status?.repo_url ? `${status.repo_url.replace(/\/$/, "")}/commit` : "";

  return (
    <div className="space-y-4">
      {/* Status card */}
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <ArrowUpCircle className="h-4 w-4 text-gray-500" />
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Software Updates</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => checkMutation.mutate()}
              disabled={checkMutation.isPending || isLoading || !!status?.update_in_progress}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-400 dark:hover:bg-gray-800"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", checkMutation.isPending && "animate-spin")} />
              Check now
            </button>
            {status?.update_available && (
              <button
                onClick={() => applyMutation.mutate()}
                disabled={applyMutation.isPending || !!status?.update_in_progress}
                className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600 disabled:opacity-50"
              >
                <ArrowUpCircle className={cn("h-3.5 w-3.5", applyMutation.isPending && "animate-spin")} />
                {status?.update_in_progress ? "Updating…" : "Apply update"}
              </button>
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-0 divide-x divide-gray-100 dark:divide-gray-800 sm:grid-cols-4">
            {[
              { label: "Current", value: status?.current_commit || "—" },
              { label: "Latest", value: status?.latest_commit || "—" },
              {
                label: "Status",
                value: status?.update_in_progress
                  ? "Updating…"
                  : status?.update_available
                    ? "Update available"
                    : "Up to date",
                accent: status?.update_in_progress
                  ? "text-blue-600 dark:text-blue-400"
                  : status?.update_available
                    ? "text-amber-600 dark:text-amber-400 font-semibold"
                    : "text-green-600 dark:text-green-400",
              },
              {
                label: "Last checked",
                value: status?.last_checked
                  ? new Date(status.last_checked).toLocaleTimeString()
                  : "—",
              },
            ].map(({ label, value, accent }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs text-gray-400 dark:text-gray-500">{label}</p>
                <p className={cn("mt-0.5 font-mono text-sm text-gray-800 dark:text-gray-200", accent)}>
                  {value}
                </p>
              </div>
            ))}
          </div>
        )}

        {resultBadge && (
          <div className={cn(
            "flex items-center gap-2 border-t px-4 py-2 text-xs",
            resultBadge === "success"
              ? "border-green-100 bg-green-50 text-green-700 dark:border-green-900/40 dark:bg-green-900/20 dark:text-green-300"
              : "border-amber-100 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-300",
          )}>
            {resultBadge === "success"
              ? <CheckCheck className="h-3.5 w-3.5 shrink-0" />
              : <AlertTriangle className="h-3.5 w-3.5 shrink-0" />}
            Last update result: <strong className="ml-0.5">{resultBadge}</strong>
            {status?.last_update_at && (
              <span className="ml-auto opacity-70">{new Date(status.last_update_at).toLocaleString()}</span>
            )}
          </div>
        )}
      </div>

      {/* Repo config */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Repository Source</h3>
          <button
            onClick={() => saveConfigMutation.mutate()}
            disabled={!isConfigDirty || saveConfigMutation.isPending || !!status?.update_in_progress}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saveConfigMutation.isPending ? "Saving…" : "Save source"}
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <label className="text-xs text-gray-500 dark:text-gray-400">
            Repo URL
            <input
              value={repoUrl}
              onChange={(e) => {
                setRepoUrl(e.target.value);
                setIsConfigDirty(true);
              }}
              placeholder="https://github.com/owner/repo"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none ring-0 placeholder:text-gray-400 focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
            />
          </label>
          <label className="text-xs text-gray-500 dark:text-gray-400">
            Branch
            <input
              value={branch}
              onChange={(e) => {
                setBranch(e.target.value);
                setIsConfigDirty(true);
              }}
              placeholder="main"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none ring-0 placeholder:text-gray-400 focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
            />
          </label>
        </div>
      </div>

      {/* Version + commit graph */}
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Version Graph</h3>
        </div>

        <div className="grid grid-cols-1 gap-3 border-b border-gray-100 px-4 py-3 text-xs text-gray-600 dark:border-gray-800 dark:text-gray-300 sm:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/40">
            <p className="text-gray-500 dark:text-gray-400">Current version</p>
            <p className="mt-1 font-mono text-sm">{status?.current_version || "No tag"}</p>
            <p className="mt-0.5 font-mono text-[11px] opacity-75">
              {commitBaseUrl && status?.current_commit ? (
                <a
                  href={`${commitBaseUrl}/${status.current_commit}`}
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-dotted hover:text-blue-600 dark:hover:text-blue-400"
                >
                  {status.current_commit}
                </a>
              ) : (
                status?.current_commit || "—"
              )}
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/40">
            <p className="text-gray-500 dark:text-gray-400">Latest version</p>
            <p className="mt-1 font-mono text-sm">{status?.latest_version || "No release tag"}</p>
            <p className="mt-0.5 font-mono text-[11px] opacity-75">
              {commitBaseUrl && status?.latest_commit ? (
                <a
                  href={`${commitBaseUrl}/${status.latest_commit}`}
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-dotted hover:text-blue-600 dark:hover:text-blue-400"
                >
                  {status.latest_commit}
                </a>
              ) : (
                status?.latest_commit || "—"
              )}
            </p>
          </div>
        </div>

        {status?.commit_graph?.length ? (
          <ol className="space-y-0 px-4 py-3">
            {status.commit_graph.map((commit, idx) => {
              const nodeClass = commit.is_latest
                ? "bg-green-500"
                : commit.is_current
                  ? "bg-blue-500"
                  : commit.is_behind_path
                    ? "bg-amber-500"
                    : "bg-gray-300 dark:bg-gray-600";
              return (
                <li key={`${commit.sha}-${idx}`} className="relative pl-7 pb-4 last:pb-0">
                  {idx < status.commit_graph.length - 1 && (
                    <span className="absolute left-[11px] top-4 h-[calc(100%-0.25rem)] w-px bg-gray-200 dark:bg-gray-700" />
                  )}
                  <span className={cn("absolute left-2 top-1.5 h-2.5 w-2.5 rounded-full", nodeClass)} />
                  <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/30">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {commitBaseUrl && commit.sha ? (
                        <a
                          href={`${commitBaseUrl}/${commit.sha}`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-[11px] text-gray-500 underline decoration-dotted hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
                        >
                          {commit.sha}
                        </a>
                      ) : (
                        <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">{commit.sha || "—"}</span>
                      )}
                      {commit.is_current && (
                        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                          Current
                        </span>
                      )}
                      {commit.is_latest && (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700 dark:bg-green-900/40 dark:text-green-300">
                          Latest
                        </span>
                      )}
                      {!commit.is_current && !commit.is_latest && commit.is_behind_path && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                          Between
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-gray-700 dark:text-gray-200">{commit.message || "No message"}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                      {commit.author || "unknown"}
                      {commit.date ? ` • ${new Date(commit.date).toLocaleString()}` : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="px-4 py-4 text-xs text-gray-500 dark:text-gray-400">
            No commit graph data available yet. Save a GitHub repo URL and run Check now.
          </p>
        )}
      </div>

      {/* Update log */}
      {status && status.log.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <div className="border-b border-gray-200 px-4 py-2 dark:border-gray-700">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">Update log</p>
          </div>
          <pre className="max-h-72 overflow-y-auto p-4 font-mono text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
            {status.log.join("\n")}
          </pre>
        </div>
      )}

      {/* Config reminder */}
      <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-700 dark:border-blue-900/40 dark:bg-blue-900/20 dark:text-blue-300">
        <p className="mb-1 font-medium">Configuration</p>
        <p>
          You can save the source repo above (URL or owner/repo) and use Check now to refresh.
          Set <code className="rounded bg-blue-100 px-1 dark:bg-blue-900/40">AUTO_UPDATE_ENABLED=true</code> for automated updates.
        </p>
      </div>
    </div>
  );
}

function LogsPanel() {
  const [category, setCategory] = useState<"all" | "server" | "login" | "action">("all");
  const [dockerService, setDockerService] = useState<string>("all");
  const [dockerTail, setDockerTail] = useState<number>(400);
  const { data: logs = [], isLoading, refetch, isFetching, error } = useQuery<DashboardLogEntry[]>({
    queryKey: ["logs", category],
    queryFn: () =>
      api
        .get<DashboardLogEntry[]>("/logs", {
          params: category !== "all" ? { category } : {},
        })
        .then((r) => r.data),
    refetchInterval: 30_000,
    retry: false,
  });
  const {
    data: dockerLogs,
    isLoading: isDockerLoading,
    isFetching: isDockerFetching,
    error: dockerError,
    refetch: refetchDockerLogs,
  } = useQuery<DockerLogsData>({
    queryKey: ["system", "docker-logs", dockerService, dockerTail],
    queryFn: () =>
      api
        .get<DockerLogsData>("/system/docker-logs", {
          params: {
            ...(dockerService !== "all" ? { service: dockerService } : {}),
            tail: dockerTail,
          },
        })
        .then((r) => r.data),
    refetchInterval: 30_000,
    retry: false,
  });

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Dashboard Logs</h2>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          </button>
        </div>
        <div className="flex gap-2 border-b border-gray-100 px-4 py-2 dark:border-gray-800">
          {(["all", "server", "login", "action"] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={cn(
                "rounded px-3 py-1 text-xs font-medium capitalize",
                category === c
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                  : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800",
              )}
            >
              {c === "all" ? "All" : c}
            </button>
          ))}
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : error ? (
          <div className="px-4 py-12 text-center text-sm text-red-500 dark:text-red-400">
            {getErrorDetail(error, "Failed to load dashboard logs.")}
          </div>
        ) : logs.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">No logs yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-100 bg-gray-50 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-800/50 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-2 text-left">Time</th>
                  <th className="px-4 py-2 text-left">Category</th>
                  <th className="px-4 py-2 text-left">Level</th>
                  <th className="px-4 py-2 text-left">Action</th>
                  <th className="px-4 py-2 text-left">User</th>
                  <th className="px-4 py-2 text-left">IP</th>
                  <th className="px-4 py-2 text-left">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium capitalize", CATEGORY_COLORS[log.category] ?? "bg-gray-100 text-gray-600")}>
                        {log.category}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium capitalize", LEVEL_COLORS[log.level] ?? "bg-gray-100 text-gray-600")}>
                        {log.level}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{log.action}</td>
                    <td className="px-4 py-2 text-xs text-gray-600 dark:text-gray-400">{log.username ?? "—"}</td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400">{log.ip_address ?? "—"}</td>
                    <td className="max-w-xs truncate px-4 py-2 text-xs text-gray-600 dark:text-gray-300" title={log.message}>{log.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <div>
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Docker Compose Logs</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Raw `docker compose logs --no-color` output from the deployed stack.
            </p>
          </div>
          <button
            onClick={() => refetchDockerLogs()}
            disabled={isDockerFetching}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
          >
            <RefreshCw className={`h-4 w-4 ${isDockerFetching ? "animate-spin" : ""}`} />
          </button>
        </div>
        <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-3 text-xs dark:border-gray-800 sm:flex-row sm:items-center">
          <label className="flex items-center gap-2">
            <span className="text-gray-500 dark:text-gray-400">Service</span>
            <select
              value={dockerService}
              onChange={(e) => setDockerService(e.target.value)}
              className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="all">All services</option>
              {(dockerLogs?.services ?? []).map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-gray-500 dark:text-gray-400">Tail</span>
            <select
              value={String(dockerTail)}
              onChange={(e) => setDockerTail(Number(e.target.value))}
              className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {[200, 400, 800, 1500, 3000].map((value) => (
                <option key={value} value={value}>
                  {value} lines
                </option>
              ))}
            </select>
          </label>
        </div>
        {isDockerLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : dockerError ? (
          <div className="px-4 py-12 text-center text-sm text-red-500 dark:text-red-400">
            {getErrorDetail(dockerError, "Failed to load docker compose logs.")}
          </div>
        ) : (
          <pre className="max-h-[34rem] overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-gray-700 dark:text-gray-300">
            {dockerLogs?.logs?.trim() || "No docker logs returned."}
          </pre>
        )}
      </div>
    </div>
  );
}

const emptyForm: ServerFormValues = {
  name: "",
  url: "",
  client_id: "",
  client_secret: "",
  ai_client_id: "",
  ai_client_secret: "",
};

// -----------------------------------------------------------------------
// Privilege preview data
// -----------------------------------------------------------------------

const READONLY_PRIVILEGES = [
  "Read Computers", "Read Computer Inventory Collection",
  "Read Smart Computer Groups", "Read Static Computer Groups",
  "Read Mobile Devices", "Read Mobile Device Inventory Collection",
  "Read Smart Mobile Device Groups", "Read Static Mobile Device Groups",
  "Read Policies", "Read Categories",
  "Read Departments", "Read Buildings", "Read Sites", "Read Scripts",
  "Read Computer Extension Attributes", "Read Mobile Device Extension Attributes",
  "Read Patch Management Software Titles",
  "Read Patch Policies", "Read Advanced Computer Searches",
];

const FULL_EXTRA_PRIVILEGES = [
  "Create / Update / Delete Computers",
  "Create / Update / Delete Policies",
  "Create / Update / Delete Smart & Static Computer Groups",
  "Create / Update / Delete Smart & Static Mobile Device Groups",
  "Create / Update / Delete Scripts",
  "Create / Update / Delete Computer Extension Attributes",
  "Send Computer Remote Lock & Wipe Commands",
];

// -----------------------------------------------------------------------
// Provision wizard
// -----------------------------------------------------------------------

interface ProvisionResult {
  server: JamfServer;
  admin_role: string;
  admin_client_display_name: string;
  readonly_role: string;
  readonly_client_display_name: string;
}

type WizardStep = "form" | "preset" | "preview" | "done";

function ProvisionWizard({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [step, setStep] = useState<WizardStep>("form");
  const [result, setResult] = useState<ProvisionResult | null>(null);
  const [form, setForm] = useState({
    server_name: "",
    jamf_url: "",
    username: "",
    password: "",
    preset: "full" as "readonly" | "full",
  });

  const provisionMutation = useMutation<ProvisionResult, Error>({
    mutationFn: () =>
      api
        .post<ProvisionResult>("/servers/provision", form)
        .then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setStep("done");
      onDone();
      toast.success(`"${data.server.name}" connected and credentials saved`);
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Provisioning failed";
      toast.error(msg);
    },
  });

  const field = (
    key: keyof typeof form,
    label: string,
    placeholder: string,
    type = "text",
  ) => (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      <input
        type={type}
        value={form[key]}
        autoComplete={type === "password" ? "current-password" : "off"}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl dark:bg-gray-900">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-gray-200 px-6 py-4 dark:border-gray-700">
          <Wand2 className="h-5 w-5 text-blue-600" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Jamf Pro Setup Wizard
          </h2>
          {/* Step indicator */}
          <div className="ml-auto flex items-center gap-1 text-xs text-gray-400">
            {(["form", "preset", "preview", "done"] as WizardStep[]).map((s, i) => (
              <span key={s} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="h-3 w-3" />}
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5",
                    step === s
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                      : "text-gray-400",
                  )}
                >
                  {i + 1}
                </span>
              </span>
            ))}
          </div>
        </div>

        <div className="px-6 py-5">
          {/* ---- Step 1: Connection form ---- */}
          {step === "form" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Enter your Jamf Pro admin credentials. They are used once to create
                API roles and clients — they are <strong>never stored</strong>.
              </p>
              <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                <span className="mt-0.5 shrink-0">ⓘ</span>
                <span>
                  <strong>SSO users:</strong> these credentials must be a{" "}
                  <strong>local Jamf Pro account</strong>. SSO/directory accounts have no
                  local password and will be rejected by the API. If your admin account is
                  SSO-only, create a temporary local admin in{" "}
                  <em>Settings → System → User Accounts &amp; Groups</em>.
                  The failover URL is not needed — the API bypasses SSO.
                </span>
              </div>
              {field("server_name", "Display name", "Production Jamf Pro")}
              {field("jamf_url", "Jamf Pro URL", "https://yourorg.jamfcloud.com")}
              <div className="grid grid-cols-2 gap-3">
                {field("username", "Admin username", "admin")}
                {field("password", "Admin password", "••••••••", "password")}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={onClose}
                  className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                >
                  Cancel
                </button>
                <button
                  onClick={() => setStep("preset")}
                  disabled={!form.server_name || !form.jamf_url || !form.username || !form.password}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  Preview what will be created
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {/* ---- Step 2: Preset selection ---- */}
          {step === "preset" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Choose which API client(s) to create on{" "}
                <span className="font-medium text-gray-700 dark:text-gray-200">{form.jamf_url}</span>.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Read Only card */}
                <button
                  onClick={() => { setForm((f) => ({ ...f, preset: "readonly" })); setStep("preview"); }}
                  className={cn(
                    "rounded-xl border-2 p-5 text-left transition hover:shadow-md",
                    form.preset === "readonly"
                      ? "border-green-500 bg-green-50 dark:border-green-500 dark:bg-green-900/20"
                      : "border-gray-200 hover:border-green-400 dark:border-gray-700 dark:hover:border-green-600",
                  )}
                >
                  <div className="mb-2 flex items-center gap-2">
                    <ShieldCheck className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <span className="font-semibold text-gray-900 dark:text-white">Read Only</span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    AI assistant only. Can read devices, policies, groups and patches.
                    Cannot modify anything. Best when you only need the AI chat feature.
                  </p>
                  <p className="mt-2 text-xs font-medium text-green-700 dark:text-green-400">
                    Creates 1 role &amp; 1 client
                  </p>
                </button>

                {/* Read + Write card */}
                <button
                  onClick={() => { setForm((f) => ({ ...f, preset: "full" })); setStep("preview"); }}
                  className={cn(
                    "rounded-xl border-2 p-5 text-left transition hover:shadow-md",
                    form.preset === "full"
                      ? "border-orange-500 bg-orange-50 dark:border-orange-500 dark:bg-orange-900/20"
                      : "border-gray-200 hover:border-orange-400 dark:border-gray-700 dark:hover:border-orange-600",
                  )}
                >
                  <div className="mb-2 flex items-center gap-2">
                    <ShieldAlert className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                    <span className="font-semibold text-gray-900 dark:text-white">Read + Write</span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Full sync + AI. All read privileges plus create, update, delete,
                    and MDM commands. Required for scheduled data sync.
                  </p>
                  <p className="mt-2 text-xs font-medium text-orange-700 dark:text-orange-400">
                    Creates 2 roles &amp; 2 clients
                  </p>
                </button>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setStep("form")}
                  className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                >
                  Back
                </button>
              </div>
            </div>
          )}

          {/* ---- Step 3: Privilege preview ---- */}
          {step === "preview" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {form.preset === "full"
                  ? "The wizard will create the following two API roles and clients on"
                  : "The wizard will create the following API role and client on"}{" "}
                <span className="font-medium text-gray-700 dark:text-gray-200">{form.jamf_url}</span>:
              </p>

              <div className={cn("grid gap-4", form.preset === "full" && "sm:grid-cols-2")}>
                {/* Read-Only card */}
                <div className="rounded-xl border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20">
                  <div className="mb-2 flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-green-600 dark:text-green-400" />
                    <span className="text-sm font-semibold text-green-800 dark:text-green-300">
                      Read-Only
                    </span>
                  </div>
                  <p className="mb-2 text-xs text-green-700 dark:text-green-400">
                    Used by the AI assistant module
                  </p>
                  <ul className="space-y-0.5">
                    {READONLY_PRIVILEGES.map((p) => (
                      <li key={p} className="flex items-center gap-1.5 text-xs text-green-700 dark:text-green-400">
                        <CheckCircle className="h-3 w-3 shrink-0" />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Full Access card — only shown for full preset */}
                {form.preset === "full" && (
                  <div className="rounded-xl border border-orange-200 bg-orange-50 p-4 dark:border-orange-800 dark:bg-orange-900/20">
                    <div className="mb-2 flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                      <span className="text-sm font-semibold text-orange-800 dark:text-orange-300">
                        Full Access
                      </span>
                    </div>
                    <p className="mb-2 text-xs text-orange-700 dark:text-orange-400">
                      Used for scheduled data sync — everything in Read-Only, plus:
                    </p>
                    <ul className="space-y-0.5">
                      {FULL_EXTRA_PRIVILEGES.map((p) => (
                        <li key={p} className="flex items-center gap-1.5 text-xs text-orange-700 dark:text-orange-400">
                          <CheckCircle className="h-3 w-3 shrink-0" />
                          {p}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <p className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                {form.preset === "full"
                  ? <>Role names: &ldquo;Jamf AI Dashboard - Read Only&rdquo; and &ldquo;Jamf AI Dashboard - Admin&rdquo;. If these roles already exist in Jamf Pro they will be reused.</>
                  : <>Role name: &ldquo;Jamf AI Dashboard - Read Only&rdquo;. If this role already exists in Jamf Pro it will be reused.</>}
              </p>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setStep("preset")}
                  className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                >
                  Back
                </button>
                <button
                  onClick={() => provisionMutation.mutate()}
                  disabled={provisionMutation.isPending}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {provisionMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  {provisionMutation.isPending ? "Creating…" : "Create roles & connect"}
                </button>
              </div>
            </div>
          )}

          {/* ---- Step 3: Success ---- */}
          {step === "done" && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-8 w-8 text-green-500" />
                <div>
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {result.server.name} is connected!
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{result.server.url}</p>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
                <p className="mb-2 font-medium text-gray-700 dark:text-gray-300">Created in Jamf Pro:</p>
                <ul className="space-y-1 text-gray-600 dark:text-gray-400">
                  <li>
                    <span className="font-medium">Role:</span> {result.readonly_role}
                    <span className="ml-2 text-xs text-gray-400">→ {result.readonly_client_display_name}</span>
                  </li>
                  {form.preset === "full" && (
                  <li>
                    <span className="font-medium">Role:</span> {result.admin_role}
                    <span className="ml-2 text-xs text-gray-400">→ {result.admin_client_display_name}</span>
                  </li>
                  )}
                </ul>
                <p className="mt-3 text-xs text-gray-400">
                  Credentials are encrypted and stored. The admin password was not saved.
                </p>
              </div>
              <div className="flex justify-end">
                <button
                  onClick={onClose}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------
// Manual server modal (unchanged)
// -----------------------------------------------------------------------

function ServerModal({
  initial,
  onClose,
  onSave,
  saving,
}: {
  initial?: JamfServer | null;
  onClose: () => void;
  onSave: (v: ServerFormValues) => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<ServerFormValues>(
    initial
      ? { name: initial.name, url: initial.url, client_id: "", client_secret: "", ai_client_id: "", ai_client_secret: "" }
      : emptyForm
  );

  const field = (key: keyof ServerFormValues, label: string, placeholder: string, type = "text") => (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      <input
        type={type}
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {initial ? "Edit Jamf Server" : "Add Jamf Server"}
        </h2>
        <div className="space-y-3">
          {field("name", "Name", "My Jamf Pro")}
          {field("url", "Jamf Pro URL", "https://yourinstance.jamfcloud.com")}
          <hr className="border-gray-200 dark:border-gray-700" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            API Role credentials with read access
          </p>
          {field("client_id", "Client ID", "API client ID")}
          {field("client_secret", "Client Secret", "API client secret", "password")}
          <hr className="border-gray-200 dark:border-gray-700" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Optional: dedicated read-only credentials for the AI module
          </p>
          {field("ai_client_id", "AI Client ID (optional)", "")}
          {field("ai_client_secret", "AI Client Secret (optional)", "", "password")}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(form)}
            disabled={saving || !form.name || !form.url || (!initial && (!form.client_id || !form.client_secret))}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : initial ? "Save Changes" : "Add Server"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RoleModal({
  initial,
  permissions,
  onClose,
  onSave,
  saving,
}: {
  initial?: AppRole | null;
  permissions: PermissionOption[];
  onClose: () => void;
  onSave: (payload: { name: string; description: string; permissions: string[] }) => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>(initial?.permissions ?? []);

  const togglePermission = (permission: string) => {
    setSelectedPermissions((prev) =>
      prev.includes(permission) ? prev.filter((item) => item !== permission) : [...prev, permission],
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {initial ? "Edit Role" : "Create Role"}
        </h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Permissions</label>
            <div className="grid gap-2 sm:grid-cols-2">
              {permissions.map((permission) => (
                <label
                  key={permission.key}
                  className="flex items-start gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={selectedPermissions.includes(permission.key)}
                    onChange={() => togglePermission(permission.key)}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">{permission.key}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{permission.label}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800">Cancel</button>
          <button
            onClick={() => onSave({ name, description, permissions: selectedPermissions })}
            disabled={saving || !name.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : initial ? "Save Role" : "Create Role"}
          </button>
        </div>
      </div>
    </div>
  );
}

function UserModal({
  initial,
  roles,
  onClose,
  onSave,
  saving,
}: {
  initial?: ManagedUser | null;
  roles: AppRole[];
  onClose: () => void;
  onSave: (payload: { username?: string; email: string; password?: string; role_id: string; is_active: boolean }) => void;
  saving: boolean;
}) {
  const [username, setUsername] = useState(initial?.username ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState(initial?.role?.id ?? roles[0]?.id ?? "");
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {initial ? `Edit ${initial.username}` : "Create User"}
        </h2>
        <div className="space-y-4">
          {!initial && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Username</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {initial ? "New Password (optional)" : "Password"}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Role</label>
            <select
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {roles.map((role) => (
                <option key={role.id} value={role.id}>{role.name}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            Active account
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800">Cancel</button>
          <button
            onClick={() => onSave({ username, email, password: password || undefined, role_id: roleId, is_active: isActive })}
            disabled={saving || (!initial && !username.trim()) || !email.trim() || !roleId || (!initial && password.length < 8)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : initial ? "Save User" : "Create User"}
          </button>
        </div>
      </div>
    </div>
  );
}

function UsersRolesPanel({ canManageUsers, canManageRoles }: { canManageUsers: boolean; canManageRoles: boolean }) {
  const qc = useQueryClient();
  const [roleModal, setRoleModal] = useState<AppRole | "add" | null>(null);
  const [userModal, setUserModal] = useState<ManagedUser | "add" | null>(null);

  const { data: roles = [] } = useQuery<AppRole[]>({
    queryKey: ["roles"],
    queryFn: () => api.get<AppRole[]>("/users/roles").then((r) => r.data),
  });
  const { data: permissions = [] } = useQuery<PermissionOption[]>({
    queryKey: ["permissions-catalog"],
    queryFn: () => api.get<{ items: PermissionOption[] }>("/users/permissions").then((r) => r.data.items),
  });
  const { data: users = [], isLoading: usersLoading } = useQuery<ManagedUser[]>({
    queryKey: ["users"],
    enabled: canManageUsers,
    queryFn: () => api.get<ManagedUser[]>("/users").then((r) => r.data),
  });

  const createRole = useMutation({
    mutationFn: (body: { name: string; description: string; permissions: string[] }) => api.post("/users/roles", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["roles"] }); toast.success("Role created"); setRoleModal(null); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to create role"),
  });
  const updateRole = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string; description: string; permissions: string[] } }) => api.patch(`/users/roles/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["roles"] }); qc.invalidateQueries({ queryKey: ["users"] }); toast.success("Role updated"); setRoleModal(null); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to update role"),
  });
  const deleteRole = useMutation({
    mutationFn: (id: string) => api.delete(`/users/roles/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["roles"] }); toast.success("Role deleted"); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to delete role"),
  });
  const createUser = useMutation({
    mutationFn: (body: { username?: string; email: string; password?: string; role_id: string; is_active: boolean }) => api.post("/users", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); toast.success("User created"); setUserModal(null); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to create user"),
  });
  const updateUser = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { email: string; password?: string; role_id: string; is_active: boolean } }) => api.patch(`/users/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); toast.success("User updated"); setUserModal(null); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to update user"),
  });
  const deleteUser = useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); toast.success("User deleted"); },
    onError: (err: unknown) => toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to delete user"),
  });

  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Users</h2>
          {canManageUsers && (
            <button onClick={() => setUserModal("add")} className="flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
              <Plus className="h-4 w-4" /> Add User
            </button>
          )}
        </div>
        {!canManageUsers ? (
          <div className="px-4 py-10 text-sm text-gray-500 dark:text-gray-400">You do not have permission to manage users.</div>
        ) : usersLoading ? (
          <div className="flex items-center justify-center py-10"><RefreshCw className="h-5 w-5 animate-spin text-gray-400" /></div>
        ) : (
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {users.map((managedUser) => (
              <li key={managedUser.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{managedUser.username}</p>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs", managedUser.is_active ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400")}>{managedUser.is_active ? "active" : "disabled"}</span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{managedUser.email}</p>
                  <p className="text-xs text-gray-400">{managedUser.role?.name ?? "No role"}</p>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => setUserModal(managedUser)} className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"><Pencil className="h-4 w-4" /></button>
                  <button onClick={() => { if (confirm(`Delete user \"${managedUser.username}\"?`)) deleteUser.mutate(managedUser.id); }} className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"><Trash2 className="h-4 w-4" /></button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Roles</h2>
          {canManageRoles && (
            <button onClick={() => setRoleModal("add")} className="flex items-center gap-2 rounded-lg border border-blue-600 px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20">
              <Plus className="h-4 w-4" /> Add Role
            </button>
          )}
        </div>
        <ul className="divide-y divide-gray-200 dark:divide-gray-700">
          {roles.map((role) => (
            <li key={role.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{role.name}</p>
                    {role.is_system && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">system</span>}
                  </div>
                  {role.description && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{role.description}</p>}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {role.permissions.map((permission) => (
                      <span key={permission} className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] text-blue-700 dark:bg-blue-950 dark:text-blue-300">{permission}</span>
                    ))}
                  </div>
                </div>
                {canManageRoles && !role.is_system && (
                  <div className="flex items-center gap-1">
                    <button onClick={() => setRoleModal(role)} className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"><Pencil className="h-4 w-4" /></button>
                    <button onClick={() => { if (confirm(`Delete role \"${role.name}\"?`)) deleteRole.mutate(role.id); }} className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"><Trash2 className="h-4 w-4" /></button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {roleModal && (
        <RoleModal
          initial={roleModal === "add" ? null : roleModal}
          permissions={permissions}
          onClose={() => setRoleModal(null)}
          onSave={(payload) => {
            if (roleModal === "add") createRole.mutate(payload);
            else updateRole.mutate({ id: roleModal.id, body: payload });
          }}
          saving={createRole.isPending || updateRole.isPending}
        />
      )}

      {userModal && (
        <UserModal
          initial={userModal === "add" ? null : userModal}
          roles={roles}
          onClose={() => setUserModal(null)}
          onSave={(payload) => {
            if (userModal === "add") createUser.mutate(payload);
            else updateUser.mutate({
              id: userModal.id,
              body: {
                email: payload.email,
                password: payload.password,
                role_id: payload.role_id,
                is_active: payload.is_active,
              },
            });
          }}
          saving={createUser.isPending || updateUser.isPending}
        />
      )}
    </div>
  );
}

// -----------------------------------------------------------------------
// Page
// -----------------------------------------------------------------------

export default function SettingsPage() {
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const [modal, setModal] = useState<"add" | JamfServer | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [syncingAll, setSyncingAll] = useState(false);
  const [activeTab, setActiveTab] = useState<"servers" | "users" | "logs" | "updates">("servers");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const permissions = user?.permissions ?? [];
  const canManageSettings = permissions.includes("settings.manage") || !!user?.is_admin;
  const canManageServers = permissions.includes("servers.manage") || permissions.includes("servers.sync") || !!user?.is_admin;
  const canManageUsers = permissions.includes("users.manage") || !!user?.is_admin;
  const canManageRoles = permissions.includes("roles.manage") || !!user?.is_admin;
  const canAccessUpdates = !!user;
  const tabs = useMemo(
    () => [
      ...(canManageServers ? [{ key: "servers" as const, label: "Jamf Servers", icon: Server }] : []),
      ...((canManageUsers || canManageRoles) ? [{ key: "users" as const, label: "Users & Roles", icon: Users }] : []),
      ...(canManageSettings ? [{ key: "logs" as const, label: "Logs", icon: ScrollText }] : []),
      ...(canAccessUpdates ? [{ key: "updates" as const, label: "Updates", icon: ArrowUpCircle }] : []),
    ],
    [canAccessUpdates, canManageRoles, canManageServers, canManageSettings, canManageUsers],
  );

  useEffect(() => {
    if (tabs.length > 0 && !tabs.some((tab) => tab.key === activeTab)) {
      setActiveTab(tabs[0].key);
    }
  }, [activeTab, tabs]);

  const { data: servers = [], isLoading } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (body: ServerFormValues) => api.post("/servers", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server added"); setModal(null); },
    onError: () => toast.error("Failed to add server"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ServerFormValues> }) =>
      api.patch(`/servers/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server updated"); setModal(null); },
    onError: () => toast.error("Failed to update server"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/servers/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server removed"); },
    onError: () => toast.error("Failed to delete server"),
  });

  const syncOneMutation = useMutation({
    mutationFn: (id: string) => api.post(`/servers/${id}/sync`).then((r) => r.data),
    onMutate: (id) => setSyncingIds((prev) => new Set(prev).add(id)),
    onSuccess: (_, id) => {
      toast.success("Sync started");
      // Poll the server list until last_sync updates
      const poll = setInterval(() => {
        qc.invalidateQueries({ queryKey: ["servers"] });
      }, 3000);
      setTimeout(() => {
        clearInterval(poll);
        setSyncingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
        qc.invalidateQueries({ queryKey: ["servers"] });
      }, 30_000);
    },
    onError: (_, id) => {
      toast.error("Sync failed");
      setSyncingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
    },
  });

  const syncAllMutation = useMutation({
    mutationFn: () => api.post("/servers/sync-all").then((r) => r.data),
    onMutate: () => setSyncingAll(true),
    onSuccess: () => {
      toast.success("Sync all started");
      const poll = setInterval(() => qc.invalidateQueries({ queryKey: ["servers"] }), 3000);
      setTimeout(() => { clearInterval(poll); setSyncingAll(false); qc.invalidateQueries({ queryKey: ["servers"] }); }, 60_000);
    },
    onError: () => { toast.error("Sync all failed"); setSyncingAll(false); },
  });

  const changePasswordMutation = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.post("/auth/change-password", body),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("Password updated. Please log in again on other devices.");
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Failed to update password",
      ),
  });

  const handleSave = (form: ServerFormValues) => {
    if (modal === "add") {
      createMutation.mutate(form);
    } else if (modal && typeof modal === "object") {
      const patch: Partial<ServerFormValues> = {};
      if (form.name !== modal.name) patch.name = form.name;
      if (form.url !== modal.url) patch.url = form.url;
      if (form.client_id) patch.client_id = form.client_id;
      if (form.client_secret) patch.client_secret = form.client_secret;
      if (form.ai_client_id) patch.ai_client_id = form.ai_client_id;
      if (form.ai_client_secret) patch.ai_client_secret = form.ai_client_secret;
      updateMutation.mutate({ id: modal.id, body: patch });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Settings</h1>
        {activeTab === "servers" && canManageServers && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 rounded-lg border border-blue-600 px-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20"
          >
            <Wand2 className="h-4 w-4" />
            Setup Wizard
          </button>
          {servers.length > 0 && (
            <button
              onClick={() => syncAllMutation.mutate()}
              disabled={syncingAll}
              className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              <RotateCw className={`h-4 w-4 ${syncingAll ? "animate-spin" : ""}`} />
              {syncingAll ? "Syncing…" : "Sync All"}
            </button>
          )}
          <button
            onClick={() => setModal("add")}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Jamf Server
          </button>
        </div>
        )}
      </div>

      {tabs.length === 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          Your role can open Settings, but it does not currently grant any management actions.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium",
                    activeTab === tab.key
                      ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-900/30 dark:text-blue-300"
                      : "border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

      {activeTab === "servers" && (
        <>
      {/* Wizard callout when no servers yet */}
      {!isLoading && servers.length === 0 && canManageServers && (
        <div
          role="button"
          tabIndex={0}
          onClick={() => setShowWizard(true)}
          onKeyDown={(e) => e.key === "Enter" && setShowWizard(true)}
          className="flex cursor-pointer items-center gap-4 rounded-xl border-2 border-dashed border-blue-300 bg-blue-50 p-5 transition hover:border-blue-400 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-900/10 dark:hover:bg-blue-900/20"
        >
          <Wand2 className="h-8 w-8 shrink-0 text-blue-500" />
          <div>
            <p className="font-medium text-blue-700 dark:text-blue-300">
              Auto-configure with Setup Wizard
            </p>
            <p className="text-sm text-blue-600 dark:text-blue-400">
              Enter your Jamf Pro URL and admin credentials. The wizard creates API roles and clients for you automatically.
            </p>
          </div>
          <ChevronRight className="ml-auto h-5 w-5 text-blue-400" />
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Jamf Pro Connections
          </h2>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : servers.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <Server className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No Jamf servers connected yet. Use the Setup Wizard or add one manually.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {servers.map((s) => (
              <li key={s.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  {s.is_active ? (
                    <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
                  ) : (
                    <XCircle className="h-4 w-4 shrink-0 text-gray-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{s.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{s.url}</p>
                    {s.last_sync_error && (
                      <p className="mt-0.5 text-xs text-red-500 dark:text-red-400">
                        {s.last_sync_error}
                      </p>
                    )}
                    {s.last_sync && !s.last_sync_error && (
                      <p className="mt-0.5 text-xs text-gray-400">
                        Last sync: {new Date(s.last_sync).toLocaleString()}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    title="Sync now"
                    onClick={() => syncOneMutation.mutate(s.id)}
                    disabled={syncingIds.has(s.id)}
                    className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-blue-600 disabled:opacity-50 dark:hover:bg-gray-800"
                  >
                    <RotateCw className={`h-4 w-4 ${syncingIds.has(s.id) ? "animate-spin" : ""}`} />
                  </button>
                  <button
                    onClick={() => setModal(s)}
                    className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Remove "${s.name}"?`)) deleteMutation.mutate(s.id);
                    }}
                    className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showWizard && (
        <ProvisionWizard
          onClose={() => setShowWizard(false)}
          onDone={() => qc.invalidateQueries({ queryKey: ["servers"] })}
        />
      )}

      {modal && (
        <ServerModal
          initial={modal === "add" ? null : modal}
          onClose={() => setModal(null)}
          onSave={handleSave}
          saving={createMutation.isPending || updateMutation.isPending}
        />
      )}
        </>
      )}

      {activeTab === "users" && <UsersRolesPanel canManageUsers={canManageUsers} canManageRoles={canManageRoles} />}

      {activeTab === "logs" && <LogsPanel />}

      {activeTab === "updates" && <UpdatesPanel />}

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <KeyRound className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">My Password</h2>
        </div>
        <div className="grid gap-3 px-4 py-4 sm:max-w-xl">
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Current password"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Password must include at least one uppercase letter and one digit.
          </p>
          <div>
            <button
              onClick={() => {
                if (newPassword !== confirmPassword) {
                  toast.error("New password confirmation does not match");
                  return;
                }
                changePasswordMutation.mutate({
                  current_password: currentPassword,
                  new_password: newPassword,
                });
              }}
              disabled={
                changePasswordMutation.isPending ||
                !currentPassword ||
                !newPassword ||
                !confirmPassword
              }
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {changePasswordMutation.isPending ? "Updating..." : "Change Password"}
            </button>
          </div>
        </div>
      </div>
        </>
      )}
    </div>
  );
}
