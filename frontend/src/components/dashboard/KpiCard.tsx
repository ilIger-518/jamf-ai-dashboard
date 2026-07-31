"use client";

import type { ElementType } from "react";

interface KpiCardProps {
  label: string;
  value: number;
  sub?: string;
  icon: ElementType;
  color: string;
  alert?: boolean;
}

export function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
  alert = false,
}: KpiCardProps) {
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
          {sub ? <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{sub}</p> : null}
        </div>
        <div className={`rounded-lg p-2 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}
