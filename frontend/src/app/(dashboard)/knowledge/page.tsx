"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Plus,
  Trash2,
  RefreshCw,
  Globe,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  X,
  Settings2,
  Pause,
  Play,
  StopCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ScrapeJob {
  id: string;
  domain: string;
  max_pages: number | null;
  max_size_mb: number | null;
  topic_filter: string | null;
  status: string;
  pages_scraped: number;
  pages_found: number;
  bytes_scraped: number;
  error: string | null;
  pause_requested: boolean;
  cancel_requested: boolean;
  cpu_cap_mode: "total" | "core";
  cpu_cap_percent: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

interface ScrapeSystemInfo {
  cpu_cores: number;
  max_total_percent: number;
  max_core_percent: number;
}

interface KnowledgeSource {
  id: string;
  title: string;
  source: string;
  doc_type: string;
  chunk_count: number;
  size_bytes: number;
  ingested_at: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; icon: React.ElementType; color: string }> = {
    pending:                { label: "Pending",    icon: Clock,        color: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" },
    running:                { label: "Running",    icon: Loader2,      color: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
    completed:              { label: "Completed",  icon: CheckCircle,  color: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" },
    completed_with_errors:  { label: "Partial",    icon: AlertCircle,  color: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
    failed:                 { label: "Failed",     icon: AlertCircle,  color: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  };
  const cfg = map[status] ?? map["pending"];
  const Icon = cfg.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", cfg.color)}>
      <Icon className={cn("h-3 w-3", status === "running" && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

function NewScrapeModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [domain, setDomain] = useState("");
  const [unlimited, setUnlimited] = useState(false);
  const [maxPages, setMaxPages] = useState(100);
  const [limitSize, setLimitSize] = useState(false);
  const [maxSizeMb, setMaxSizeMb] = useState(500);
  const [topicFilter, setTopicFilter] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      api.post<ScrapeJob>("/knowledge/scrape", {
        domain,
        max_pages: unlimited ? null : maxPages,
        max_size_mb: limitSize ? maxSizeMb : null,
        topic_filter: topicFilter || null,
      }).then((r) => r.data),
    onSuccess: () => {
      toast.success("Scrape job started");
      qc.invalidateQueries({ queryKey: ["scrape-jobs"] });
      onClose();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to start scrape job";
      toast.error(msg);
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">New Scrape Job</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="h-4 w-4 text-gray-400" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              Domain / Start URL
            </label>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="https://learn.jamf.com"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
            <p className="mt-1 text-xs text-gray-400">
              The crawler stays on this domain. All linked pages are followed up to the max.
            </p>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300">
                Max pages
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={unlimited}
                  onChange={(e) => setUnlimited(e.target.checked)}
                  className="h-3.5 w-3.5 rounded accent-blue-600"
                />
                <span className="text-xs text-gray-500 dark:text-gray-400">Unlimited</span>
              </label>
            </div>
            {!unlimited && (
              <input
                type="number"
                min={1}
                value={maxPages}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              />
            )}
            {unlimited && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                ⚠ The crawler will run until the entire domain is scraped or the size limit is hit.
              </p>
            )}
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300">
                Max data size
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={limitSize}
                  onChange={(e) => setLimitSize(e.target.checked)}
                  className="h-3.5 w-3.5 rounded accent-blue-600"
                />
                <span className="text-xs text-gray-500 dark:text-gray-400">Enable limit</span>
              </label>
            </div>
            {limitSize ? (
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  value={maxSizeMb}
                  onChange={(e) => setMaxSizeMb(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                />
                <span className="text-xs text-gray-500 whitespace-nowrap">MB</span>
              </div>
            ) : (
              <p className="text-xs text-gray-400">No size limit — only page count controls stopping.</p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              Topic filter <span className="text-gray-400">(optional)</span>
            </label>
            <input
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              placeholder="e.g. patch management, MDM enrollment, FileVault…"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
            <p className="mt-1 text-xs text-gray-400">
              If set, the LLM will evaluate each page and skip ones that don't match this topic.
            </p>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!domain.trim() || mutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Start Scrape
          </button>
        </div>
      </div>
    </div>
  );
}

function JobSettingsModal({
  job,
  system,
  onClose,
  onSaved,
}: {
  job: ScrapeJob;
  system: ScrapeSystemInfo;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [mode, setMode] = useState<"total" | "core">(job.cpu_cap_mode || "total");
  const [cap, setCap] = useState<number>(job.cpu_cap_percent || 100);
  const [pendingAction, setPendingAction] = useState(false);

  const maxCap = mode === "total" ? system.max_total_percent : system.max_core_percent;

  useEffect(() => {
    if (cap > maxCap) setCap(maxCap);
  }, [maxCap, cap]);

  const submit = async (action: "pause" | "resume" | "cancel") => {
    try {
      setPendingAction(true);
      await api.patch(`/knowledge/scrape/${job.id}`, {
        action,
        cpu_cap_mode: mode,
        cpu_cap_percent: cap,
      });
      toast.success(
        action === "pause" ? "Job paused" : action === "resume" ? "Job resumed" : "Job cancelled",
      );
      onSaved();
      if (action === "cancel") onClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to update job";
      toast.error(msg);
    } finally {
      setPendingAction(false);
    }
  };

  const saveCap = async () => {
    try {
      setPendingAction(true);
      await api.patch(`/knowledge/scrape/${job.id}`, {
        action: job.pause_requested ? "pause" : "resume",
        cpu_cap_mode: mode,
        cpu_cap_percent: cap,
      });
      toast.success("CPU cap updated");
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to update CPU cap";
      toast.error(msg);
    } finally {
      setPendingAction(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">Job Settings</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="h-4 w-4 text-gray-400" />
          </button>
        </div>

        <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">{job.domain}</p>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">CPU Mode</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setMode("total")}
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm",
                  mode === "total"
                    ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-900/30 dark:text-blue-300"
                    : "border-gray-300 text-gray-600 dark:border-gray-600 dark:text-gray-300",
                )}
              >
                Total CPU (1-100%)
              </button>
              <button
                onClick={() => setMode("core")}
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm",
                  mode === "core"
                    ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-900/30 dark:text-blue-300"
                    : "border-gray-300 text-gray-600 dark:border-gray-600 dark:text-gray-300",
                )}
              >
                Linux style (1-{system.max_core_percent}%)
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              CPU Cap: {cap}%
            </label>
            <input
              type="range"
              min={1}
              max={maxCap}
              value={cap}
              onChange={(e) => setCap(Number(e.target.value))}
              className="w-full"
            />
            <div className="mt-1 flex justify-between text-[11px] text-gray-400">
              <span>1%</span>
              <span>{maxCap}%</span>
            </div>
            <button
              onClick={saveCap}
              disabled={pendingAction}
              className="mt-2 rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              Save CPU Cap
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2 pt-1">
            {job.pause_requested ? (
              <button
                onClick={() => submit("resume")}
                disabled={pendingAction}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" /> Resume
              </button>
            ) : (
              <button
                onClick={() => submit("pause")}
                disabled={pendingAction}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-amber-600 px-3 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                <Pause className="h-3.5 w-3.5" /> Pause
              </button>
            )}

            <div />

            <button
              onClick={() => submit("cancel")}
              disabled={pendingAction}
              className="inline-flex items-center justify-center gap-1 rounded-lg bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              <StopCircle className="h-3.5 w-3.5" /> Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  const qc = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [settingsJob, setSettingsJob] = useState<ScrapeJob | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: jobs = [], isLoading: jobsLoading } = useQuery<ScrapeJob[]>({
    queryKey: ["scrape-jobs"],
    queryFn: () => api.get<ScrapeJob[]>("/knowledge/scrape").then((r) => r.data),
  });

  const { data: sources = [], isLoading: sourcesLoading } = useQuery<KnowledgeSource[]>({
    queryKey: ["knowledge-sources"],
    queryFn: () => api.get<KnowledgeSource[]>("/knowledge/sources").then((r) => r.data),
  });

  const { data: systemInfo } = useQuery<ScrapeSystemInfo>({
    queryKey: ["scrape-system-info"],
    queryFn: () => api.get<ScrapeSystemInfo>("/knowledge/scrape/system").then((r) => r.data),
  });

  const deleteJob = useMutation({
    mutationFn: (id: string) => api.delete(`/knowledge/scrape/${id}`),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["scrape-jobs"] });
    },
    onError: () => toast.error("Failed to delete job"),
  });

  const deleteSource = useMutation({
    mutationFn: (id: string) => api.delete(`/knowledge/sources/${id}`),
    onSuccess: () => {
      toast.success("Source deleted");
      qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
    onError: () => toast.error("Failed to delete source"),
  });

  // Poll while any job is running or pending
  const hasActiveJob = jobs.some((j) => j.status === "running" || j.status === "pending");
  useEffect(() => {
    if (hasActiveJob) {
      pollingRef.current = setInterval(() => {
        qc.invalidateQueries({ queryKey: ["scrape-jobs"] });
        qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
      }, 3000);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [hasActiveJob, qc]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Knowledge Base</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Scrape websites and store them locally so the AI assistant can answer questions from them.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          New Scrape
        </button>
      </div>

      {showModal && <NewScrapeModal onClose={() => setShowModal(false)} />}
      {settingsJob && systemInfo && (
        <JobSettingsModal
          job={settingsJob}
          system={systemInfo}
          onClose={() => setSettingsJob(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["scrape-jobs"] });
            qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
          }}
        />
      )}

      {/* Scrape Jobs */}
      <section>
        <h2 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">Scrape Jobs</h2>
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          {jobsLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <Globe className="h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="text-sm text-gray-500 dark:text-gray-400">No scrape jobs yet. Click "New Scrape" to get started.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>
                  {["Domain", "Topic Filter", "Progress", "Status", "Finished", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="max-w-xs truncate px-4 py-3 font-medium text-gray-900 dark:text-white" title={job.domain}>
                      {job.domain.replace(/^https?:\/\//, "")}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs italic">
                      {job.topic_filter ?? <span className="not-italic text-gray-300 dark:text-gray-600">all pages</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      <div>
                        {job.pages_scraped} {job.max_pages !== null ? `/ ${job.max_pages} pages` : "pages (∞)"}
                      </div>
                      <div className="text-gray-400">
                        {(job.bytes_scraped / 1048576).toFixed(1)} MB
                        {job.max_size_mb !== null ? ` / ${job.max_size_mb} MB` : ""}
                      </div>
                      {job.status === "running" && job.max_pages !== null && (
                        <div className="mt-1 h-1 w-24 rounded-full bg-gray-200 dark:bg-gray-700">
                          <div
                            className="h-1 rounded-full bg-blue-500 transition-all"
                            style={{ width: `${Math.min(100, (job.pages_scraped / job.max_pages) * 100)}%` }}
                          />
                        </div>
                      )}
                      {job.status === "running" && job.max_size_mb !== null && (
                        <div className="mt-1 h-1 w-24 rounded-full bg-gray-200 dark:bg-gray-700">
                          <div
                            className="h-1 rounded-full bg-green-500 transition-all"
                            style={{ width: `${Math.min(100, (job.bytes_scraped / (job.max_size_mb * 1048576)) * 100)}%` }}
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                      {job.error && (
                        <p className="mt-0.5 text-xs text-red-500 dark:text-red-400 max-w-xs truncate" title={job.error}>
                          {job.error}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {(job.status === "pending" || job.status === "running") && (
                        <button
                          onClick={() => setSettingsJob(job)}
                          className="mr-2 inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                        >
                          <Settings2 className="h-3.5 w-3.5" />
                          Settings
                        </button>
                      )}
                      {job.status !== "pending" && job.status !== "running" && (
                        <button
                          onClick={() => {
                            if (confirm(`Delete this scrape job for "${job.domain.replace(/^https?:\/\//, "")}"?`)) {
                              deleteJob.mutate(job.id);
                            }
                          }}
                          className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
                          title="Delete job"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Stored Sources */}
      <section>
        <h2 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          Stored Sources{" "}
          <span className="ml-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            {sources.length}
          </span>
        </h2>
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          {sourcesLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          ) : sources.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <BookOpen className="h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No documents ingested yet. Run a scrape job to populate the knowledge base.
              </p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>
                  {["Title", "URL", "Chunks", "Size", "Ingested", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {sources.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="max-w-xs truncate px-4 py-3 font-medium text-gray-900 dark:text-white" title={s.title}>
                      {s.title}
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-xs text-blue-600 dark:text-blue-400" title={s.source}>
                      <a href={s.source} target="_blank" rel="noreferrer noopener" className="hover:underline">
                        {s.source.replace(/^https?:\/\//, "").slice(0, 60)}
                        {s.source.length > 67 ? "…" : ""}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{s.chunk_count}</td>
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                      {formatBytes(s.size_bytes)}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(s.ingested_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => {
                          if (confirm(`Delete "${s.title}" from the knowledge base?`)) {
                            deleteSource.mutate(s.id);
                          }
                        }}
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
                        title="Delete source"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
