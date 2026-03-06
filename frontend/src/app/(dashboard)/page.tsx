"use client";

import { useQuery } from "@tanstack/react-query";
import { Monitor, Shield, Package, Users, Server, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

interface Stats {
  total_devices: number;
  managed_devices: number;
  total_policies: number;
  enabled_policies: number;
  total_patches: number;
  unpatched_count: number;
  total_smart_groups: number;
  total_servers: number;
  active_servers: number;
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: number;
  sub?: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p className="mt-1 text-3xl font-semibold text-gray-900 dark:text-white">{value.toLocaleString()}</p>
          {sub && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
        </div>
        <div className={`rounded-lg p-2 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

export default function DashboardHomePage() {
  const { data, isLoading } = useQuery<Stats>({
    queryKey: ["dashboard", "stats"],
    queryFn: () => api.get<Stats>("/dashboard/stats").then((r) => r.data),
    refetchInterval: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="flex h-48 items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Dashboard</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Total Devices"
          value={data.total_devices}
          sub={`${data.managed_devices} managed`}
          icon={Monitor}
          color="bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400"
        />
        <StatCard
          label="Policies"
          value={data.total_policies}
          sub={`${data.enabled_policies} enabled`}
          icon={Shield}
          color="bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
        />
        <StatCard
          label="Patch Titles"
          value={data.total_patches}
          sub={data.unpatched_count > 0 ? `${data.unpatched_count} unpatched devices` : "All patched"}
          icon={Package}
          color="bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400"
        />
        <StatCard
          label="Smart Groups"
          value={data.total_smart_groups}
          icon={Users}
          color="bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400"
        />
        <StatCard
          label="Jamf Servers"
          value={data.total_servers}
          sub={`${data.active_servers} active`}
          icon={Server}
          color="bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
        />
      </div>

      {data.total_servers === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center dark:border-gray-700 dark:bg-gray-900/50">
          <Server className="mx-auto mb-3 h-8 w-8 text-gray-400" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">No Jamf servers connected</p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Go to{" "}
            <a href="/settings" className="text-blue-600 hover:underline dark:text-blue-400">
              Settings
            </a>{" "}
            to add a Jamf Pro connection.
          </p>
        </div>
      )}
    </div>
  );
}
