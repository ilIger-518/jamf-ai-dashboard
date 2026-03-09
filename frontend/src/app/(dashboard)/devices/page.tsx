"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Monitor, RefreshCw, Search, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";

interface Device {
  id: string;
  name: string;
  serial_number: string | null;
  model: string | null;
  os_version: string | null;
  is_managed: boolean;
  is_supervised: boolean;
  last_contact: string | null;
  username: string | null;
  department: string | null;
}

interface DeviceDetail extends Device {
  jamf_id: number;
  asset_tag: string | null;
  model_identifier: string | null;
  processor: string | null;
  ram_mb: number | null;
  os_build: string | null;
  last_enrollment: string | null;
  full_name: string | null;
  email: string | null;
  building: string | null;
  site: string | null;
  server_url: string | null;
  synced_at: string;
}

interface PagedDevices {
  items: Device[];
  total: number;
  page: number;
  per_page: number;
}

function fmt(dt: string | null | undefined) {
  return dt ? new Date(dt).toLocaleString() : "—";
}

export default function DevicesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const perPage = 50;

  const { data, isLoading } = useQuery<PagedDevices>({
    queryKey: ["devices", page, search],
    queryFn: () =>
      api
        .get<PagedDevices>("/devices", { params: { page, per_page: perPage, search: search || undefined } })
        .then((r) => r.data),
  });

  const { data: detail, isLoading: detailLoading } = useQuery<DeviceDetail>({
    queryKey: ["devices", selectedId],
    queryFn: () => api.get<DeviceDetail>(`/devices/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Devices</h1>
        {data && <span className="text-sm text-gray-500">{data.total.toLocaleString()} total</span>}
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search by name, serial, or user…"
          className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
        />
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Monitor className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {search ? "No devices match your search." : "No devices yet. Connect a Jamf server in Settings."}
            </p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>
                  {["Name", "Serial", "Model", "OS", "User", "Department", "Last Contact", "Status"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase dark:text-gray-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.items.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => setSelectedId(d.id)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.name}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">{d.serial_number ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.model ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.os_version ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.username ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.department ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {d.last_contact ? new Date(d.last_contact).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                        d.is_managed
                          ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                          : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                      )}>
                        {d.is_managed ? "Managed" : "Unmanaged"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 dark:border-gray-700">
                <span className="text-xs text-gray-500">Page {page} of {totalPages}</span>
                <div className="flex gap-2">
                  <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800">Previous</button>
                  <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800">Next</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <DetailDrawer
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        title={detail?.name ?? "Device Details"}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : detail ? (
          <div className="space-y-6 px-6 py-4">
            <DrawerSection title="Identity">
              <DrawerRow label="Name" value={detail.name} />
              <DrawerRow label="Jamf ID" value={
                detail.server_url
                  ? <a href={`${detail.server_url}/computers.html?id=${detail.jamf_id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline dark:text-blue-400">{detail.jamf_id} <ExternalLink className="h-3 w-3" /></a>
                  : detail.jamf_id
              } />
              <DrawerRow label="Serial Number" value={<span className="font-mono text-xs">{detail.serial_number ?? "—"}</span>} />
              <DrawerRow label="Asset Tag" value={detail.asset_tag} />
            </DrawerSection>

            <DrawerSection title="Hardware">
              <DrawerRow label="Model" value={detail.model} />
              <DrawerRow label="Model Identifier" value={<span className="font-mono text-xs">{detail.model_identifier}</span>} />
              <DrawerRow label="Processor" value={detail.processor} />
              <DrawerRow label="RAM" value={detail.ram_mb ? `${(detail.ram_mb / 1024).toFixed(0)} GB` : null} />
            </DrawerSection>

            <DrawerSection title="Operating System">
              <DrawerRow label="Version" value={detail.os_version} />
              <DrawerRow label="Build" value={<span className="font-mono text-xs">{detail.os_build}</span>} />
            </DrawerSection>

            <DrawerSection title="Management">
              <DrawerRow label="Managed" value={
                <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  detail.is_managed ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" : "bg-gray-100 text-gray-500")}>
                  {detail.is_managed ? "Managed" : "Unmanaged"}
                </span>
              } />
              <DrawerRow label="Supervised" value={detail.is_supervised ? "Yes" : "No"} />
              <DrawerRow label="Last Contact" value={fmt(detail.last_contact)} />
              <DrawerRow label="Last Enrollment" value={fmt(detail.last_enrollment)} />
            </DrawerSection>

            <DrawerSection title="User">
              <DrawerRow label="Username" value={detail.username} />
              <DrawerRow label="Full Name" value={detail.full_name} />
              <DrawerRow label="Email" value={detail.email} />
              <DrawerRow label="Department" value={detail.department} />
              <DrawerRow label="Building" value={detail.building} />
              <DrawerRow label="Site" value={detail.site} />
            </DrawerSection>

            <p className="text-xs text-gray-400 pb-2">Last synced {fmt(detail.synced_at)}</p>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
