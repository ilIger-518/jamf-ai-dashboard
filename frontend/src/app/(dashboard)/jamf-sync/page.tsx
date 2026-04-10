"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  Box,
  CheckCircle2,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface JamfServer {
  id: string;
  name: string;
  is_active: boolean;
}

interface PackageItem {
  id: number;
  name: string;
  filename: string | null;
  category: string | null;
}

interface PackageSyncItemResult {
  package_id: number;
  name: string;
  status: "created" | "skipped" | "failed";
  message: string | null;
  logs: string[];
  file_status: "transferred" | "skipped" | "failed" | null;
  file_message: string | null;
}

interface PackageSyncServerResult {
  target_server_id: string;
  target_server_name: string;
  created: number;
  skipped: number;
  failed: number;
  results: PackageSyncItemResult[];
}

interface PackageSyncResponse {
  source_server_id: string;
  servers: PackageSyncServerResult[];
}

export default function JamfSyncPage() {
  const [sourceServerId, setSourceServerId] = useState("");
  const [targetServerIds, setTargetServerIds] = useState<string[]>([]);
  const [selectedPackageIds, setSelectedPackageIds] = useState<number[]>([]);
  const [skipExisting, setSkipExisting] = useState(true);
  const [transferFile, setTransferFile] = useState(false);
  const [lastResult, setLastResult] = useState<PackageSyncResponse | null>(null);
  const [selectedItemResult, setSelectedItemResult] = useState<PackageSyncItemResult | null>(null);

  const { data: servers = [], isLoading: serversLoading } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
  });

  const {
    data: packages = [],
    isLoading: packagesLoading,
    isError: packagesError,
    error: packagesErrorValue,
    refetch: refetchPackages,
  } = useQuery<PackageItem[]>({
    queryKey: ["package-sync", "packages", sourceServerId],
    enabled: !!sourceServerId,
    queryFn: () =>
      api
        .get<PackageItem[]>("/package-sync/packages", {
          params: { server_id: sourceServerId },
        })
        .then((r) => r.data),
  });

  const copyMutation = useMutation<PackageSyncResponse, Error>({
    mutationFn: () =>
      api
        .post<PackageSyncResponse>("/package-sync/copy", {
          source_server_id: sourceServerId,
          target_server_ids: targetServerIds,
          package_ids: selectedPackageIds,
          skip_existing: skipExisting,
          transfer_file: transferFile,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setLastResult(data);
      const totalCreated = data.servers.reduce((s, r) => s + r.created, 0);
      const totalSkipped = data.servers.reduce((s, r) => s + r.skipped, 0);
      const totalFailed = data.servers.reduce((s, r) => s + r.failed, 0);
      toast.success(
        `Copy completed: ${totalCreated} created, ${totalSkipped} skipped, ${totalFailed} failed`,
      );
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Package copy failed";
      toast.error(msg);
    },
  });

  const packagesErrorMessage =
    (packagesErrorValue as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ??
    (packagesErrorValue as Error | undefined)?.message ??
    "Failed to load packages from source server";

  const allChecked =
    packages.length > 0 && selectedPackageIds.length === packages.length;

  const canRun = useMemo(
    () =>
      !!sourceServerId &&
      targetServerIds.length > 0 &&
      selectedPackageIds.length > 0 &&
      !copyMutation.isPending,
    [sourceServerId, targetServerIds.length, selectedPackageIds.length, copyMutation.isPending],
  );

  const onToggleAll = () => {
    setSelectedPackageIds(allChecked ? [] : packages.map((p) => p.id));
  };

  const onTogglePackage = (id: number) => {
    setSelectedPackageIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const onToggleTarget = (id: string) => {
    setTargetServerIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const availableTargets = servers.filter((s) => s.id !== sourceServerId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Jamf Sync</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Copy package records from one Jamf Pro server to one or more target servers.
          </p>
        </div>
      </div>

      {/* Server selection */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="grid gap-4 md:grid-cols-2">
          {/* Source */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Source server
            </label>
            <select
              value={sourceServerId}
              onChange={(e) => {
                setSourceServerId(e.target.value);
                setSelectedPackageIds([]);
                setLastResult(null);
                setTargetServerIds((prev) => prev.filter((id) => id !== e.target.value));
              }}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">Select source…</option>
              {servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {!s.is_active ? " (inactive)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Targets */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Target server(s)
            </label>
            {availableTargets.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {sourceServerId
                  ? "No other servers available."
                  : "Select a source server first."}
              </p>
            ) : (
              <div className="max-h-36 space-y-1 overflow-auto rounded-lg border border-gray-300 p-2 dark:border-gray-600">
                {availableTargets.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-2 text-sm text-gray-700 dark:text-gray-300"
                  >
                    <input
                      type="checkbox"
                      checked={targetServerIds.includes(s.id)}
                      onChange={() => onToggleTarget(s.id)}
                    />
                    {s.name}
                    {!s.is_active ? " (inactive)" : ""}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
            />
            Skip packages that already exist on target
          </label>
          <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={transferFile}
              onChange={(e) => setTransferFile(e.target.checked)}
            />
            Also transfer package file (requires JDCS2)
          </label>
        </div>

        {!transferFile && (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
            Only package <strong>records</strong> (metadata) will be copied. Enable{" "}
            <em>Also transfer package file</em> to also move the binary via the Jamf Pro v1 JDCS2
            API, or transfer files manually using Jamf Admin / Jamf Sync.
          </p>
        )}
      </div>

      {/* Package list */}
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
            Packages{sourceServerId ? ` from ${servers.find((s) => s.id === sourceServerId)?.name}` : ""}
          </div>
          <button
            onClick={() => refetchPackages()}
            disabled={!sourceServerId || packagesLoading}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            {packagesLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Reload
          </button>
        </div>

        {!sourceServerId ? (
          <div className="px-4 py-10 text-sm text-gray-500 dark:text-gray-400">
            Select a source server to load packages.
          </div>
        ) : packagesLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : packagesError ? (
          <div className="px-4 py-10 text-sm text-red-600 dark:text-red-400">
            {packagesErrorMessage}
          </div>
        ) : packages.length === 0 ? (
          <div className="flex flex-col items-center px-4 py-10 text-sm text-gray-500 dark:text-gray-400">
            <Box className="mb-2 h-8 w-8 text-gray-300 dark:text-gray-600" />
            No packages found on this server.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={allChecked} onChange={onToggleAll} />
                Select all
              </label>
              <span>{selectedPackageIds.length} selected</span>
            </div>
            <div className="max-h-[360px] overflow-auto border-t border-gray-100 dark:border-gray-800">
              {packages.map((pkg) => (
                <label
                  key={pkg.id}
                  className="flex cursor-pointer items-center gap-3 border-b border-gray-100 px-4 py-2 text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedPackageIds.includes(pkg.id)}
                    onChange={() => onTogglePackage(pkg.id)}
                  />
                  <span className="text-gray-500 dark:text-gray-400">#{pkg.id}</span>
                  <span className="flex-1 text-gray-900 dark:text-gray-100">{pkg.name}</span>
                  {pkg.filename && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">{pkg.filename}</span>
                  )}
                  {pkg.category && (
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      {pkg.category}
                    </span>
                  )}
                </label>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="text-sm text-gray-600 dark:text-gray-300">
          {sourceServerId && targetServerIds.length > 0
            ? `Copy ${selectedPackageIds.length} package(s) to ${targetServerIds.length} server(s)`
            : "Choose source, select target server(s), then select packages to copy."}
        </div>
        <button
          onClick={() => copyMutation.mutate()}
          disabled={!canRun}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {copyMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRightLeft className="h-4 w-4" />
          )}
          Copy Packages
        </button>
      </div>

      {/* Results */}
      {lastResult && (
        <div className="space-y-4">
          {lastResult.servers.map((serverResult) => (
            <div
              key={serverResult.target_server_id}
              className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
            >
              <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700">
                <div className="text-sm font-medium text-gray-900 dark:text-white">
                  {serverResult.target_server_name}
                </div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Created: {serverResult.created} | Skipped: {serverResult.skipped} | Failed:{" "}
                  {serverResult.failed}
                </div>
                <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                  Click an item to view full logs.
                </div>
              </div>
              <div className="max-h-[280px] overflow-auto">
                {serverResult.results.map((r) => (
                  <button
                    key={`${serverResult.target_server_id}-${r.package_id}-${r.status}`}
                    type="button"
                    onClick={() => setSelectedItemResult(r)}
                    className="w-full border-b border-gray-100 px-4 py-2 text-left text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/40"
                  >
                    <span
                      className={cn(
                        "mr-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs",
                        r.status === "created" &&
                          "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
                        r.status === "skipped" &&
                          "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
                        r.status === "failed" &&
                          "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                      )}
                    >
                      {r.status === "created" && <CheckCircle2 className="h-3 w-3" />}
                      {r.status === "failed" && <XCircle className="h-3 w-3" />}
                      {r.status}
                    </span>
                    {r.file_status && (
                      <span
                        className={cn(
                          "mr-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs",
                          r.file_status === "transferred" &&
                            "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
                          r.file_status === "skipped" &&
                            "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
                          r.file_status === "failed" &&
                            "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                        )}
                      >
                        file: {r.file_status}
                      </span>
                    )}
                    <span className="font-medium text-gray-900 dark:text-white">{r.name}</span>
                    {r.message && (
                      <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                        {r.message}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Log detail modal */}
      {selectedItemResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-3xl rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">
                  Package Copy Details
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  #{selectedItemResult.package_id} {selectedItemResult.name}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedItemResult(null)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Close
              </button>
            </div>

            <div className="space-y-4 p-4">
              <div>
                <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Status
                </div>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs",
                    selectedItemResult.status === "created" &&
                      "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
                    selectedItemResult.status === "skipped" &&
                      "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
                    selectedItemResult.status === "failed" &&
                      "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                  )}
                >
                  {selectedItemResult.status}
                </span>
                {selectedItemResult.file_status && (
                  <span
                    className={cn(
                      "ml-2 rounded px-1.5 py-0.5 text-xs",
                      selectedItemResult.file_status === "transferred" &&
                        "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
                      selectedItemResult.file_status === "skipped" &&
                        "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
                      selectedItemResult.file_status === "failed" &&
                        "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                    )}
                  >
                    file: {selectedItemResult.file_status}
                  </span>
                )}
                {selectedItemResult.message && (
                  <p className="mt-2 whitespace-pre-wrap rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
                    {selectedItemResult.message}
                  </p>
                )}
                {selectedItemResult.file_message && (
                  <p
                    className={cn(
                      "mt-2 whitespace-pre-wrap rounded border p-2 text-xs",
                      selectedItemResult.file_status === "failed"
                        ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
                        : "border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400",
                    )}
                  >
                    {selectedItemResult.file_message}
                  </p>
                )}
              </div>

              <div>
                <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Logs
                </div>
                <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-3 font-mono text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200">
                  {(selectedItemResult.logs ?? []).join("\n") || "No logs recorded"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {serversLoading && (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}
    </div>
  );
}

