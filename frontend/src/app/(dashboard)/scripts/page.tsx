"use client";

import { useQuery } from "@tanstack/react-query";
import { FileCode2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useUiStore } from "@/store/uiStore";

interface ScriptItem {
  id: number;
  name: string;
  category: string | null;
}

export default function ScriptsPage() {
  const { selectedServerId } = useUiStore();

  const { data = [], isLoading } = useQuery<ScriptItem[]>({
    queryKey: ["assets", "scripts", selectedServerId],
    enabled: !!selectedServerId,
    queryFn: () =>
      api
        .get<ScriptItem[]>("/assets/scripts", { params: { server_id: selectedServerId } })
        .then((r) => r.data),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Scripts</h1>
        <span className="text-sm text-gray-500">{data.length.toLocaleString()} total</span>
      </div>

      {!selectedServerId ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
          Select a server from the top-left server selector to view scripts.
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center rounded-xl border border-gray-200 bg-white py-16 dark:border-gray-700 dark:bg-gray-900">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center dark:border-gray-700 dark:bg-gray-900">
          <FileCode2 className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No scripts found on this Jamf server.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {data.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{s.id}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{s.name}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{s.category || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
