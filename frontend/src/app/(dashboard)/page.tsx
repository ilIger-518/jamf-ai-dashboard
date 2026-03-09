"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Monitor,
  Shield,
  Package,
  Users,
  Server,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { api } from "@/lib/api";
import { OsVersionChart } from "@/components/dashboard/OsVersionChart";
import { PatchStatusBar } from "@/components/dashboard/PatchStatusBar";

interface OsVersionCount {
  os_version: string;
  count: number;
}

interface PatchSummary {
  software_title: string;
  patched: number;
  unpatched: number;
}

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
  os_distribution: OsVersionCount[];
  top_patches: PatchSummary[];
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
  alert = false,
}: {
  label: string;
  value: number;
  sub?: string;
  icon: React.ElementType;
  color: string;
  alert?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-white p-5 dark:bg-gray-900 ${
        alert && value > 0
          ? "border-red-200 dark:border-red-900"
          : "border-gray-200 dark:border-gray-700"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p
            className={`mt-1 text-3xl font-semibold ${
              alert && value > 0
                ? "text-red-600 dark:text-red-400"
                : "text-gray-900 dark:text-white"
            }`}
          >
            {value.toLocaleString()}
          </p>
          {sub && (
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{sub}</p>
          )}
        </div>
        <div className={`rounded-lg p-2 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {title}
      </h2>
      {children}
    </div>
  );
}

export default function DashboardHomePage() {
  const qc = useQueryClient();
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const { data, isLoading } = useQuery<Stats>({
    queryKey: ["dashboard", "stats"],
    queryFn: async () => {
      const r = await api.get<Stats>("/dashboard/stats");
      setLastFetch(new Date());
      return r.data;
    },
    refetchInterval: 300_000,
  });

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await qc.refetchQueries({ queryKey: ["dashboard", "stats"] });
    setIsRefreshing(false);
  };

  if (isLoading || !data) {
    return (
      <div className="flex h-48 items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  const unmanaged = data.total_devices - data.managed_devices;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <div className="flex items-center gap-3">
          {lastFetch && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              Updated {formatDistanceToNow(lastFetch, { addSuffix: true })}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Total Devices"
          value={data.total_devices}
          sub={`${data.managed_devices.toLocaleString()} managed`}
          icon={Monitor}
          color="bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400"
        />
        <StatCard
          label="Unmanaged"
          value={unmanaged}
          sub={unmanaged > 0 ? "Need attention" : "All managed"}
          icon={AlertCircle}
          color="bg-red-50 text-red-500 dark:bg-red-950 dark:text-red-400"
          alert={true}
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
          sub={
            data.unpatched_count > 0
              ? `${data.unpatched_count.toLocaleString()} unpatched`
              : "All up to date"
          }
          icon={Package}
          color={
            data.unpatched_count > 0
              ? "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400"
              : "bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400"
          }
          alert={data.unpatched_count > 0}
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

      {/* Charts */}
      {data.total_devices > 0 && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ChartCard title="OS Version Distribution">
            <OsVersionChart data={data.os_distribution} />
          </ChartCard>
          <ChartCard title="Patch Status · Top Titles">
            <PatchStatusBar data={data.top_patches} />
          </ChartCard>
        </div>
      )}

      {/* No servers empty state */}
      {data.total_servers === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center dark:border-gray-700 dark:bg-gray-900/50">
          <Server className="mx-auto mb-3 h-8 w-8 text-gray-400" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            No Jamf servers connected
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Go to{" "}
            <a
              href="/settings"
              className="text-blue-600 hover:underline dark:text-blue-400"
            >
              Settings
            </a>{" "}
            to add a Jamf Pro connection.
          </p>
        </div>
      )}
    </div>
  );
}
