"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, RefreshCw, Search } from "lucide-react";
import { api } from "@/lib/api";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";

interface Criterion {
  name?: string;
  priority?: number;
  and_or?: string;
  search_type?: string;
  value?: string;
}

interface SmartGroup {
  id: string;
  name: string;
  member_count: number;
  last_refreshed: string | null;
  criteria: unknown[] | null;
}

interface SmartGroupDetail extends SmartGroup {
  jamf_id: number;
  criteria: Criterion[] | null;
  synced_at: string;
}

interface PagedSmartGroups { items: SmartGroup[]; total: number; page: number; per_page: number; }

function fmt(dt: string | null | undefined) {
  return dt ? new Date(dt).toLocaleString() : "—";
}

export default function SmartGroupsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const perPage = 50;

  const { data, isLoading } = useQuery<PagedSmartGroups>({
    queryKey: ["smart-groups", page, search],
    queryFn: () => api.get<PagedSmartGroups>("/smart-groups", { params: { page, per_page: perPage, search: search || undefined } }).then((r) => r.data),
  });

  const { data: detail, isLoading: detailLoading } = useQuery<SmartGroupDetail>({
    queryKey: ["smart-groups", selectedId],
    queryFn: () => api.get<SmartGroupDetail>(`/smart-groups/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Smart Groups</h1>
        {data && <span className="text-sm text-gray-500">{data.total.toLocaleString()} total</span>}
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search smart groups…" className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {isLoading ? (
          <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 animate-spin text-gray-400" /></div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Users className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">{search ? "No smart groups match your search." : "No smart groups yet. Connect a Jamf server in Settings."}</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>{["Name", "Members", "Criteria", "Last Refreshed"].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.items.map((g) => (
                  <tr
                    key={g.id}
                    onClick={() => setSelectedId(g.id)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{g.name}</td>
                    <td className="px-4 py-3 text-gray-500">{g.member_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{g.criteria ? `${g.criteria.length} rule${g.criteria.length !== 1 ? "s" : ""}` : "—"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{g.last_refreshed ? new Date(g.last_refreshed).toLocaleString() : "—"}</td>
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
        title={detail?.name ?? "Smart Group Details"}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : detail ? (
          <div className="space-y-6 px-6 py-4">
            <DrawerSection title="Group">
              <DrawerRow label="Name" value={detail.name} />
              <DrawerRow label="Jamf ID" value={detail.jamf_id} />
              <DrawerRow label="Members" value={detail.member_count.toLocaleString()} />
              <DrawerRow label="Last Refreshed" value={fmt(detail.last_refreshed)} />
            </DrawerSection>

            {detail.criteria && detail.criteria.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                  Criteria ({detail.criteria.length})
                </p>
                <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 dark:bg-gray-800">
                      <tr>
                        {["Field", "Operator", "Value"].map((h) => (
                          <th key={h} className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {detail.criteria.map((c, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{c.name ?? "—"}</td>
                          <td className="px-3 py-2 text-gray-500">{c.search_type ?? "—"}</td>
                          <td className="px-3 py-2 text-gray-700 dark:text-gray-300 break-all">{c.value ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <p className="text-xs text-gray-400 pb-2">Last synced {fmt(detail.synced_at)}</p>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
