"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shield, RefreshCw, Search, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";
import { useUiStore } from "@/store/uiStore";

interface Policy {
  id: string;
  name: string;
  enabled: boolean;
  category: string | null;
  trigger: string | null;
  scope_description: string | null;
}

interface PolicyDetail extends Policy {
  jamf_id: number;
  server_url: string | null;
  synced_at: string;
}

interface PagedPolicies { items: Policy[]; total: number; page: number; per_page: number; }

function fmt(dt: string | null | undefined) {
  return dt ? new Date(dt).toLocaleString() : "—";
}

export default function PoliciesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const perPage = 50;
  const { selectedServerId } = useUiStore();

  useEffect(() => { setPage(1); }, [selectedServerId]);

  const { data, isLoading } = useQuery<PagedPolicies>({
    queryKey: ["policies", page, search, selectedServerId],
    queryFn: () => api.get<PagedPolicies>("/policies", { params: { page, per_page: perPage, search: search || undefined, server_id: selectedServerId || undefined } }).then((r) => r.data),
  });

  const { data: detail, isLoading: detailLoading } = useQuery<PolicyDetail>({
    queryKey: ["policies", selectedId],
    queryFn: () => api.get<PolicyDetail>(`/policies/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Policies</h1>
        {data && <span className="text-sm text-gray-500">{data.total.toLocaleString()} total</span>}
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search policies…" className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {isLoading ? (
          <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 animate-spin text-gray-400" /></div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Shield className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">{search ? "No policies match your search." : "No policies yet. Connect a Jamf server in Settings."}</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>{["Name", "Category", "Trigger", "Status"].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.items.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{p.name}</td>
                    <td className="px-4 py-3 text-gray-500">{p.category ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">{p.trigger ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", p.enabled ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400")}>
                        {p.enabled ? "Enabled" : "Disabled"}
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
        title={detail?.name ?? "Policy Details"}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : detail ? (
          <div className="space-y-6 px-6 py-4">
            <DrawerSection title="Policy">
              <DrawerRow label="Name" value={detail.name} />
              <DrawerRow label="Jamf ID" value={
                detail.server_url
                  ? <a href={`${detail.server_url}/policies.html?id=${detail.jamf_id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline dark:text-blue-400">{detail.jamf_id} <ExternalLink className="h-3 w-3" /></a>
                  : detail.jamf_id
              } />
              <DrawerRow label="Status" value={
                <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  detail.enabled ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" : "bg-gray-100 text-gray-500")}>
                  {detail.enabled ? "Enabled" : "Disabled"}
                </span>
              } />
              <DrawerRow label="Category" value={detail.category} />
              <DrawerRow label="Trigger" value={detail.trigger ? <span className="font-mono text-xs">{detail.trigger}</span> : null} />
            </DrawerSection>

            {detail.scope_description && (
              <DrawerSection title="Scope">
                <div className="py-2 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {detail.scope_description}
                </div>
              </DrawerSection>
            )}

            <p className="text-xs text-gray-400 pb-2">Last synced {fmt(detail.synced_at)}</p>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
