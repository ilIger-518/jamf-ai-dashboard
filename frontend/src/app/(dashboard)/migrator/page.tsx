"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRightLeft, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type EntityType = "policy" | "smart_group" | "static_group" | "script";

interface JamfServer {
  id: string;
  name: string;
  is_active: boolean;
}

interface MigratorObject {
  id: number;
  name: string;
  entity_type: EntityType;
}

interface ListMigratorObjectsResponse {
  items: MigratorObject[];
}

interface MigrationItemResult {
  object_id: number;
  name: string;
  status: "created" | "skipped" | "failed";
  message: string | null;
  logs: string[];
}

interface MigrationResponse {
  entity_type: EntityType;
  source_server_id: string;
  target_server_id: string;
  created: number;
  skipped: number;
  failed: number;
  results: MigrationItemResult[];
}

const ENTITY_OPTIONS: { label: string; value: EntityType; helper: string }[] = [
  { label: "Policies", value: "policy", helper: "Classic policies and settings" },
  { label: "Smart Groups", value: "smart_group", helper: "Computer groups with criteria" },
  { label: "Scripts", value: "script", helper: "Script payloads and metadata" },
  {
    label: "Static Groups",
    value: "static_group",
    helper: "Computer groups with fixed members",
  },
];

export default function MigratorPage() {
  const [entityType, setEntityType] = useState<EntityType>("policy");
  const [sourceServerId, setSourceServerId] = useState("");
  const [targetServerId, setTargetServerId] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [skipExisting, setSkipExisting] = useState(true);
  const [includeStaticMembers, setIncludeStaticMembers] = useState(false);
  const [migrateDependencies, setMigrateDependencies] = useState(true);
  const [lastResult, setLastResult] = useState<MigrationResponse | null>(null);
  const [selectedResult, setSelectedResult] = useState<MigrationItemResult | null>(null);

  const { data: servers = [], isLoading: serversLoading } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
  });

  const {
    data: objects,
    isLoading: objectsLoading,
    isError: objectsError,
    error: objectsErrorValue,
    refetch,
  } = useQuery<ListMigratorObjectsResponse>({
    queryKey: ["migrator", "objects", sourceServerId, entityType],
    enabled: !!sourceServerId,
    queryFn: () =>
      api
        .get<ListMigratorObjectsResponse>("/migrator/objects", {
          params: { source_server_id: sourceServerId, entity_type: entityType },
        })
        .then((r) => r.data),
  });

  const migrateMutation = useMutation<MigrationResponse, Error>({
    mutationFn: () =>
      api
        .post<MigrationResponse>("/migrator/migrate", {
          source_server_id: sourceServerId,
          target_server_id: targetServerId,
          entity_type: entityType,
          object_ids: selectedIds,
          skip_existing: skipExisting,
          include_static_members: includeStaticMembers,
          migrate_dependencies: migrateDependencies,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setLastResult(data);
      toast.success(`Migration completed: ${data.created} created, ${data.skipped} skipped, ${data.failed} failed`);
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Migration failed";
      toast.error(msg);
    },
  });

  const allObjects = objects?.items ?? [];
  const objectsErrorMessage =
    (objectsErrorValue as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (objectsErrorValue as Error | undefined)?.message ??
    "Failed to load objects from source server";
  const allChecked = allObjects.length > 0 && selectedIds.length === allObjects.length;

  const canRunMigration = useMemo(
    () =>
      !!sourceServerId &&
      !!targetServerId &&
      sourceServerId !== targetServerId &&
      selectedIds.length > 0 &&
      !migrateMutation.isPending,
    [sourceServerId, targetServerId, selectedIds.length, migrateMutation.isPending],
  );

  const onToggleAll = () => {
    if (allChecked) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(allObjects.map((o) => o.id));
  };

  const onToggleOne = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const sourceName = servers.find((s) => s.id === sourceServerId)?.name;
  const targetName = servers.find((s) => s.id === targetServerId)?.name;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Migrator</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Migrate policies, smart groups, and static groups between Jamf Pro servers.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Source server</label>
            <select
              value={sourceServerId}
              onChange={(e) => {
                setSourceServerId(e.target.value);
                setSelectedIds([]);
                setLastResult(null);
              }}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">Select source...</option>
              {servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {!s.is_active ? " (inactive)" : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Target server</label>
            <select
              value={targetServerId}
              onChange={(e) => {
                setTargetServerId(e.target.value);
                setLastResult(null);
              }}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">Select target...</option>
              {servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {!s.is_active ? " (inactive)" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {ENTITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                setEntityType(opt.value);
                setSelectedIds([]);
                setLastResult(null);
              }}
              className={cn(
                "rounded-lg border px-3 py-2 text-left transition",
                entityType === opt.value
                  ? "border-blue-500 bg-blue-50 dark:border-blue-500 dark:bg-blue-900/30"
                  : "border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600",
              )}
            >
              <div className="text-sm font-medium text-gray-900 dark:text-white">{opt.label}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">{opt.helper}</div>
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
            />
            Skip objects that already exist on target
          </label>

          <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={includeStaticMembers}
              onChange={(e) => setIncludeStaticMembers(e.target.checked)}
              disabled={entityType !== "static_group"}
            />
            Include static group members
          </label>

          <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={migrateDependencies}
              onChange={(e) => setMigrateDependencies(e.target.checked)}
              disabled={entityType !== "policy"}
            />
            Migrate dependencies (scripts and groups used by policy)
          </label>
        </div>

        <div className="mt-4 flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">
          <ArrowRightLeft className="h-3.5 w-3.5" />
          With dependencies enabled, missing policy scripts/groups are copied first and policy references are remapped.
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
            Source objects {sourceName ? `from ${sourceName}` : ""}
          </div>
          <button
            onClick={() => refetch()}
            disabled={!sourceServerId || objectsLoading}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            {objectsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Reload
          </button>
        </div>

        {!sourceServerId ? (
          <div className="px-4 py-10 text-sm text-gray-500 dark:text-gray-400">Select a source server to load objects.</div>
        ) : objectsLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : objectsError ? (
          <div className="px-4 py-10 text-sm text-red-600 dark:text-red-400">{objectsErrorMessage}</div>
        ) : allObjects.length === 0 ? (
          <div className="px-4 py-10 text-sm text-gray-500 dark:text-gray-400">No objects found for this type.</div>
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={allChecked} onChange={onToggleAll} />
                Select all
              </label>
              <span>{selectedIds.length} selected</span>
            </div>
            <div className="max-h-[360px] overflow-auto border-t border-gray-100 dark:border-gray-800">
              {allObjects.map((obj) => (
                <label
                  key={obj.id}
                  className="flex cursor-pointer items-center gap-3 border-b border-gray-100 px-4 py-2 text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(obj.id)}
                    onChange={() => onToggleOne(obj.id)}
                  />
                  <span className="text-gray-500 dark:text-gray-400">#{obj.id}</span>
                  <span className="text-gray-900 dark:text-gray-100">{obj.name}</span>
                </label>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="text-sm text-gray-600 dark:text-gray-300">
          {sourceName && targetName
            ? `Migrate ${selectedIds.length} ${entityType.replace("_", " ")} object(s) from ${sourceName} to ${targetName}`
            : "Choose source and target servers, then select objects to migrate."}
        </div>
        <button
          onClick={() => migrateMutation.mutate()}
          disabled={!canRunMigration}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {migrateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRightLeft className="h-4 w-4" />}
          Run Migration
        </button>
      </div>

      {lastResult && (
        <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700">
            <div className="text-sm font-medium text-gray-900 dark:text-white">Last Migration Result</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Created: {lastResult.created} | Skipped: {lastResult.skipped} | Failed: {lastResult.failed}
            </div>
            <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">Click an item to view full logs.</div>
          </div>
          <div className="max-h-[320px] overflow-auto">
            {lastResult.results.map((r) => (
              <button
                key={`${r.object_id}-${r.status}-${r.name}`}
                type="button"
                onClick={() => setSelectedResult(r)}
                className="w-full border-b border-gray-100 px-4 py-2 text-left text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/40"
              >
                <span
                  className={cn(
                    "mr-2 rounded px-1.5 py-0.5 text-xs",
                    r.status === "created" && "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
                    r.status === "skipped" && "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
                    r.status === "failed" && "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                  )}
                >
                  {r.status}
                </span>
                <span className="font-medium text-gray-900 dark:text-white">{r.name}</span>
                {r.message && <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">{r.message}</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {selectedResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-3xl rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">Migration Item Details</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">#{selectedResult.object_id} {selectedResult.name}</div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedResult(null)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Close
              </button>
            </div>

            <div className="space-y-4 p-4">
              <div>
                <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Status</div>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs",
                    selectedResult.status === "created" && "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
                    selectedResult.status === "skipped" && "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
                    selectedResult.status === "failed" && "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
                  )}
                >
                  {selectedResult.status}
                </span>
                {selectedResult.message && (
                  <p className="mt-2 whitespace-pre-wrap rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
                    {selectedResult.message}
                  </p>
                )}
              </div>

              <div>
                <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Logs</div>
                <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-3 font-mono text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200">
                  {(selectedResult.logs ?? []).join("\n") || "No logs recorded"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {serversLoading && (
        <div className="text-xs text-gray-500 dark:text-gray-400">Loading server list...</div>
      )}
    </div>
  );
}
