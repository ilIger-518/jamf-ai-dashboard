"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface PatchSummary {
  software_title: string;
  patched: number;
  unpatched: number;
}

const truncate = (s: string, n = 26) => (s.length > n ? s.slice(0, n) + "…" : s);

export function PatchStatusBar({ data }: { data: PatchSummary[] }) {
  if (!data.length) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        No patch data yet
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    label: truncate(d.software_title),
  }));

  const height = Math.max(data.length * 40, 160);

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ left: 4, right: 28, top: 4, bottom: 4 }}
        >
          <XAxis
            type="number"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12 }}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={148}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              borderRadius: "8px",
              border: "1px solid #e5e7eb",
              boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
              fontSize: "13px",
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
          />
          <Bar dataKey="patched" name="Patched" stackId="a" fill="#22c55e" />
          <Bar
            dataKey="unpatched"
            name="Unpatched"
            stackId="a"
            fill="#ef4444"
            radius={[0, 4, 4, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
