"use client";

import { useQuery } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { Box, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useUiStore } from "@/store/uiStore";

interface PackageItem {
  id: number;
  name: string;
  filename: string | null;
  category: string | null;
}

export default function PackagesPage() {
  const { selectedServerId } = useUiStore();

  const { data = [], isLoading, isError, error } = useQuery<PackageItem[]>({
    queryKey: ["assets", "packages", selectedServerId],
    enabled: !!selectedServerId,
    queryFn: () =>
      api
        .get<PackageItem[]>("/assets/packages", { params: { server_id: selectedServerId } })
        .then((r) => r.data),
  });

  const errorMessage = (() => {
    if (!isError) return null;
    const err = error as AxiosError<{ detail?: string }> | null;
    return err?.response?.data?.detail || err?.message || "Unable to load packages from Jamf Pro.";
  })();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Packages</h1>
        <span className="text-sm text-gray-500">{data.length.toLocaleString()} total</span>
      </div>

      {!selectedServerId ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
          Select a server from the top-left server selector to view packages.
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center rounded-xl border border-gray-200 bg-white py-16 dark:border-gray-700 dark:bg-gray-900">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
          Failed to load packages. {errorMessage}
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center dark:border-gray-700 dark:bg-gray-900">
          <Box className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No packages found on this Jamf server.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Filename</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {data.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{p.id}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{p.name}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{p.filename || "—"}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{p.category || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
