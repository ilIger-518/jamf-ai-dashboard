"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Device {
  id: string;
  name: string;
  serial_number: string | null;
  os_version: string | null;
  username: string | null;
  is_managed: boolean;
}

interface PagedDevices { items: Device[]; total: number; page: number; per_page: number; }

export default function CompliancePage() {
  // Compliance summary: show managed vs unmanaged device status as a proxy
  // for actual compliance checks until M3 sync populates ComplianceResult rows.
  const { data, isLoading } = useQuery<PagedDevices>({
    queryKey: ["compliance-devices"],
    queryFn: () => api.get<PagedDevices>("/devices", { params: { per_page: 200 } }).then((r) => r.data),
  });

  const total = data?.total ?? 0;
  const managed = data?.items.filter((d) => d.is_managed).length ?? 0;
  const unmanaged = total - managed;
  const score = total > 0 ? Math.round((managed / total) * 100) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Compliance</h1>

      {isLoading ? (
        <div className="flex items-center justify-center py-16"><RefreshCw className="h-5 w-5 animate-spin text-gray-400" /></div>
      ) : total === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-gray-200 bg-white py-16 text-center dark:border-gray-700 dark:bg-gray-900">
          <ClipboardCheck className="h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm text-gray-500 dark:text-gray-400">No compliance data yet. Connect a Jamf server in Settings.</p>
        </div>
      ) : (
        <>
          {/* Score summary */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { label: "Management Score", value: `${score}%`, color: score >= 90 ? "text-green-600 dark:text-green-400" : score >= 70 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400" },
              { label: "Managed Devices", value: managed.toLocaleString(), color: "text-green-600 dark:text-green-400" },
              { label: "Unmanaged Devices", value: unmanaged.toLocaleString(), color: unmanaged > 0 ? "text-red-600 dark:text-red-400" : "text-gray-500" },
            ].map(({ label, value, color }) => (
              <div key={label} className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
                <p className={cn("mt-1 text-3xl font-semibold", color)}>{value}</p>
              </div>
            ))}
          </div>

          {/* Device table */}
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium text-gray-700 dark:border-gray-700 dark:text-gray-300">
              Device Management Status
            </div>
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>{["Device", "Serial", "OS", "User", "Status"].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data!.items.map((d) => (
                  <tr key={d.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.name}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">{d.serial_number ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.os_version ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.username ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                        d.is_managed ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300" : "bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400"
                      )}>
                        {d.is_managed ? "✓ Managed" : "✗ Unmanaged"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
