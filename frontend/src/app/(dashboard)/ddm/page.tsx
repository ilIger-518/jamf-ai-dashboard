"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Layers, RefreshCw, Search, RotateCcw, CheckCircle, XCircle, Clock, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";
import { useUiStore } from "@/store/uiStore";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DDMDevice {
  id: string;
  jamf_id: number;
  name: string;
  serial_number: string | null;
  model: string | null;
  os_version: string | null;
  username: string | null;
  department: string | null;
  last_contact: string | null;
  management_id: string | null;
  server_id: string;
}

interface PagedDDMDevices {
  items: DDMDevice[];
  total: number;
  page: number;
  per_page: number;
}

interface DDMStatusResponse {
  device_id: string;
  management_id: string;
  status_items: DDMStatusItem[];
  raw: Record<string, unknown>;
}

interface DDMStatusItem {
  identifier?: string;
  valid?: string;
  reasons?: Array<{ failureType?: string; description?: string }>;
  client?: Record<string, unknown>;
  [key: string]: unknown;
}

interface DDMSyncResponse {
  device_id: string;
  management_id: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(dt: string | null | undefined) {
  return dt ? new Date(dt).toLocaleString() : "—";
}

function StatusBadge({ valid }: { valid?: string }) {
  if (!valid) return <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"><Clock className="h-3 w-3" /> Unknown</span>;
  const lower = valid.toLowerCase();
  if (lower === "valid" || lower === "true") return <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"><CheckCircle className="h-3 w-3" /> Active</span>;
  if (lower === "invalid" || lower === "false") return <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"><XCircle className="h-3 w-3" /> Failed</span>;
  return <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300"><AlertCircle className="h-3 w-3" /> {valid}</span>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DDMPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const perPage = 50;
  const { selectedServerId } = useUiStore();
  const queryClient = useQueryClient();

  useEffect(() => { setPage(1); }, [selectedServerId]);

  // Device list
  const { data, isLoading } = useQuery<PagedDDMDevices>({
    queryKey: ["ddm-devices", page, search, selectedServerId],
    queryFn: () =>
      api
        .get<PagedDDMDevices>("/ddm/devices", {
          params: {
            page,
            per_page: perPage,
            search: search || undefined,
            server_id: selectedServerId || undefined,
          },
        })
        .then((r) => r.data),
  });

  // DDM status for selected device
  const { data: ddmStatus, isLoading: statusLoading, error: statusError } = useQuery<DDMStatusResponse>({
    queryKey: ["ddm-status", selectedId],
    queryFn: () =>
      api.get<DDMStatusResponse>(`/ddm/devices/${selectedId}/status`).then((r) => r.data),
    enabled: !!selectedId,
    retry: false,
  });

  // Force sync mutation
  const syncMutation = useMutation<DDMSyncResponse, Error, string>({
    mutationFn: (deviceId: string) =>
      api.post<DDMSyncResponse>(`/ddm/devices/${deviceId}/sync`).then((r) => r.data),
    onSuccess: (data) => {
      setSyncMessage(data.message);
      // Refresh DDM status after a short delay
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["ddm-status", selectedId] });
        setSyncMessage(null);
      }, 3000);
    },
    onError: (err) => {
      setSyncMessage(`Error: ${err.message}`);
    },
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  const selectedDevice = data?.items.find((d) => d.id === selectedId);

  // Blueprint-like items: status_items that look like blueprint declarations
  const blueprintItems = ddmStatus?.status_items?.filter(
    (item) =>
      typeof item.identifier === "string" &&
      (item.identifier.toLowerCase().includes("blueprint") ||
        item.identifier.toLowerCase().includes("declaration") ||
        item.identifier.toLowerCase().includes("configuration"))
  ) ?? [];

  const softwareUpdateItems = ddmStatus?.status_items?.filter(
    (item) =>
      typeof item.identifier === "string" &&
      (item.identifier.toLowerCase().includes("softwareupdate") ||
        item.identifier.toLowerCase().includes("software-update") ||
        item.identifier.toLowerCase().includes("osupdate"))
  ) ?? [];

  const otherItems = ddmStatus?.status_items?.filter(
    (item) =>
      !blueprintItems.includes(item) && !softwareUpdateItems.includes(item)
  ) ?? [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            DDM Status
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Declarative Device Management — Blueprint &amp; declaration status
          </p>
        </div>
        {data && (
          <span className="text-sm text-gray-500">
            {data.total.toLocaleString()} DDM-enabled devices
          </span>
        )}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search by name, serial, or user…"
          className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Layers className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {search
                ? "No DDM-enabled devices match your search."
                : "No DDM-enabled devices found. Devices need a management_id to appear here. Run a server sync to populate device data."}
            </p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>
                  {["Name", "Serial", "Model", "OS", "User", "Department", "Last Contact"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.items.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => { setSelectedId(d.id); setSyncMessage(null); }}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{d.serial_number ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.model ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.os_version ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.username ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.department ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {d.last_contact ? new Date(d.last_contact).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 dark:border-gray-700">
                <span className="text-xs text-gray-500">Page {page} of {totalPages}</span>
                <div className="flex gap-2">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    className="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800"
                  >
                    Previous
                  </button>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage(page + 1)}
                    className="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail Drawer */}
      <DetailDrawer
        open={!!selectedId}
        onClose={() => { setSelectedId(null); setSyncMessage(null); }}
        title={selectedDevice?.name ?? "DDM Details"}
      >
        <div className="space-y-6 px-6 py-4">
          {/* Device identity */}
          {selectedDevice && (
            <DrawerSection title="Device">
              <DrawerRow label="Name" value={selectedDevice.name} />
              <DrawerRow label="Serial Number" value={<span className="font-mono text-xs">{selectedDevice.serial_number ?? "—"}</span>} />
              <DrawerRow label="Model" value={selectedDevice.model} />
              <DrawerRow label="OS Version" value={selectedDevice.os_version} />
              <DrawerRow label="User" value={selectedDevice.username} />
              <DrawerRow label="Department" value={selectedDevice.department} />
              <DrawerRow label="Last Contact" value={fmt(selectedDevice.last_contact)} />
              <DrawerRow
                label="Management ID"
                value={<span className="font-mono text-xs break-all">{selectedDevice.management_id ?? "—"}</span>}
              />
            </DrawerSection>
          )}

          {/* Force Sync */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => selectedId && syncMutation.mutate(selectedId)}
              disabled={syncMutation.isPending || !selectedDevice?.management_id}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition",
                "bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              <RotateCcw className={cn("h-4 w-4", syncMutation.isPending && "animate-spin")} />
              {syncMutation.isPending ? "Syncing…" : "Force DDM Sync"}
            </button>
            {syncMessage && (
              <span className={cn(
                "text-xs",
                syncMessage.startsWith("Error") ? "text-red-500" : "text-green-600 dark:text-green-400"
              )}>
                {syncMessage}
              </span>
            )}
          </div>

          {/* DDM Status */}
          {statusLoading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          ) : statusError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30 px-4 py-3">
              <p className="text-sm text-red-700 dark:text-red-300">
                {statusError instanceof Error
                  ? statusError.message
                  : "Failed to load DDM status. DDM may not be enabled on this device."}
              </p>
            </div>
          ) : ddmStatus ? (
            <>
              {/* Blueprint / Declaration status */}
              {blueprintItems.length > 0 && (
                <DrawerSection title="Blueprints / Declarations">
                  {blueprintItems.map((item, i) => (
                    <div key={i} className="py-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all min-w-0">
                          {item.identifier ?? `Item ${i + 1}`}
                        </span>
                        <StatusBadge valid={item.valid} />
                      </div>
                      {item.reasons && item.reasons.length > 0 && (
                        <ul className="ml-2 space-y-0.5">
                          {item.reasons.map((r, ri) => (
                            <li key={ri} className="text-xs text-red-600 dark:text-red-400">
                              {r.description ?? r.failureType ?? JSON.stringify(r)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </DrawerSection>
              )}

              {/* Software Updates */}
              {softwareUpdateItems.length > 0 && (
                <DrawerSection title="Software Updates">
                  {softwareUpdateItems.map((item, i) => (
                    <div key={i} className="py-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all min-w-0">
                          {item.identifier ?? `Item ${i + 1}`}
                        </span>
                        <StatusBadge valid={item.valid} />
                      </div>
                      {item.reasons && item.reasons.length > 0 && (
                        <ul className="ml-2 space-y-0.5">
                          {item.reasons.map((r, ri) => (
                            <li key={ri} className="text-xs text-red-600 dark:text-red-400">
                              {r.description ?? r.failureType ?? JSON.stringify(r)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </DrawerSection>
              )}

              {/* Other status items */}
              {otherItems.length > 0 && (
                <DrawerSection title="Other Status Items">
                  {otherItems.map((item, i) => (
                    <div key={i} className="py-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all min-w-0">
                          {item.identifier ?? `Item ${i + 1}`}
                        </span>
                        <StatusBadge valid={item.valid} />
                      </div>
                      {item.reasons && item.reasons.length > 0 && (
                        <ul className="ml-2 space-y-0.5">
                          {item.reasons.map((r, ri) => (
                            <li key={ri} className="text-xs text-red-600 dark:text-red-400">
                              {r.description ?? r.failureType ?? JSON.stringify(r)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </DrawerSection>
              )}

              {ddmStatus.status_items.length === 0 && (
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-6 text-center">
                  <Layers className="mx-auto mb-2 h-8 w-8 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    No DDM status items found for this device.
                  </p>
                </div>
              )}

              {/* Summary counts */}
              {ddmStatus.status_items.length > 0 && (
                <div className="flex gap-4 rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-3">
                  {[
                    {
                      label: "Active",
                      count: ddmStatus.status_items.filter((i) =>
                        ["valid", "true"].includes((i.valid ?? "").toLowerCase())
                      ).length,
                      color: "text-green-600 dark:text-green-400",
                    },
                    {
                      label: "Failed",
                      count: ddmStatus.status_items.filter((i) =>
                        ["invalid", "false"].includes((i.valid ?? "").toLowerCase())
                      ).length,
                      color: "text-red-600 dark:text-red-400",
                    },
                    {
                      label: "Unknown",
                      count: ddmStatus.status_items.filter(
                        (i) =>
                          !["valid", "true", "invalid", "false"].includes(
                            (i.valid ?? "").toLowerCase()
                          )
                      ).length,
                      color: "text-gray-500",
                    },
                  ].map(({ label, count, color }) => (
                    <div key={label} className="text-center">
                      <p className={cn("text-lg font-semibold", color)}>{count}</p>
                      <p className="text-xs text-gray-500">{label}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </DetailDrawer>
    </div>
  );
}
