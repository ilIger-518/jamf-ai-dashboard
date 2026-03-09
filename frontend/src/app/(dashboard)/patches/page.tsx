"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Package, RefreshCw, Search, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";

interface Patch {
  id: string;
  software_title: string;
  current_version: string | null;
  latest_version: string | null;
  patched_count: number;
  unpatched_count: number;
  total_count: number;
  patch_percent: number;
}

interface PatchDetail extends Patch {
  jamf_id: number | null;
  server_url: string | null;
  synced_at: string;
}

interface PagedPatches { items: Patch[]; total: number; page: number; per_page: number; }

function fmt(dt: string | null | undefined) {
  return dt ? new Date(dt).toLocaleString() : "—";
}

export default function PatchesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const perPage = 50;

  const { data, isLoading } = useQuery<PagedPatches>({
    queryKey: ["patches", page, search],
    queryFn: () => api.get<PagedPatches>("/patches", { params: { page, per_page: perPage, search: search || undefined } }).then((r) => r.data),
  });

  const { data: detail, isLoading: detailLoading } = useQuery<PatchDetail>({
    queryKey: ["patches", selectedId],
    queryFn: () => api.get<PatchDetail>(`/patches/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Patch Management</h1>
        {data && <span className="text-sm text-gray-500">{data.total.toLocaleString()} titles</span>}
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search software titles…" className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {isLoading ? (
          <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 animate-spin text-gray-400" /></div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Package className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">{search ? "No patch titles match your search." : "No patch data yet. Connect a Jamf server in Settings."}</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>{["Software", "Current", "Latest", "Patched", "Unpatched", "Coverage"].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.items.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{p.software_title}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">{p.current_version ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">{p.latest_version ?? "—"}</td>
                    <td className="px-4 py-3 text-green-600 dark:text-green-400">{p.patched_count}</td>
                    <td className="px-4 py-3">
                      <span className={cn("font-medium", p.unpatched_count > 0 ? "text-red-600 dark:text-red-400" : "text-gray-400")}>{p.unpatched_count}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 rounded-full bg-gray-200 dark:bg-gray-700">
                          <div className="h-1.5 rounded-full bg-green-500" style={{ width: `${p.patch_percent}%` }} />
                        </div>
                        <span className="text-xs text-gray-500">{p.patch_percent}%</span>
                      </div>
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
        title={detail?.software_title ?? "Patch Details"}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : detail ? (
          <div className="space-y-6 px-6 py-4">
            <DrawerSection title="Software Title">
              <DrawerRow label="Title" value={detail.software_title} />
              {detail.jamf_id != null && <DrawerRow label="Jamf ID" value={
                detail.server_url
                  ? <a href={`${detail.server_url}/view/computers/patch/${detail.jamf_id}?tab=report`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline dark:text-blue-400">{detail.jamf_id} <ExternalLink className="h-3 w-3" /></a>
                  : detail.jamf_id
              } />}
              <DrawerRow label="Current Version" value={<span className="font-mono text-xs">{detail.current_version}</span>} />
              <DrawerRow label="Latest Version" value={<span className="font-mono text-xs">{detail.latest_version}</span>} />
            </DrawerSection>

            <DrawerSection title="Patch Status">
              <DrawerRow label="Total Devices" value={detail.total_count.toLocaleString()} />
              <DrawerRow label="Patched" value={
                <span className="font-medium text-green-600 dark:text-green-400">{detail.patched_count.toLocaleString()}</span>
              } />
              <DrawerRow label="Unpatched" value={
                <span className={cn("font-medium", detail.unpatched_count > 0 ? "text-red-600 dark:text-red-400" : "text-gray-400")}>
                  {detail.unpatched_count.toLocaleString()}
                </span>
              } />
              <DrawerRow label="Coverage" value={
                <div className="flex items-center gap-2">
                  <div className="h-2 w-24 rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={cn("h-2 rounded-full", detail.patch_percent >= 90 ? "bg-green-500" : detail.patch_percent >= 70 ? "bg-yellow-400" : "bg-red-500")}
                      style={{ width: `${detail.patch_percent}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium">{detail.patch_percent}%</span>
                </div>
              } />
            </DrawerSection>

            <p className="text-xs text-gray-400 pb-2">Last synced {fmt(detail.synced_at)}</p>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
