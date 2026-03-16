"use client";

import { useMemo, useState } from "react";

type ProbeResult = {
  url: string;
  ok: boolean;
  status: number;
  body: string;
};

export default function NetworkDebugPage() {
  const [results, setResults] = useState<ProbeResult[]>([]);
  const [loading, setLoading] = useState(false);

  const origin = useMemo(() => {
    if (typeof window === "undefined") return "";
    return window.location.origin;
  }, []);

  const apiBase = `${origin}/api/v1`;

  const runChecks = async () => {
    setLoading(true);
    const probes = [
      `${apiBase}/health`,
      `${apiBase}/auth/me`,
      `${origin}`,
    ];

    const next: ProbeResult[] = [];
    for (const url of probes) {
      try {
        const response = await fetch(url, {
          method: "GET",
          credentials: "include",
        });
        const text = await response.text();
        next.push({
          url,
          ok: response.ok,
          status: response.status,
          body: text.slice(0, 300),
        });
      } catch (err) {
        next.push({
          url,
          ok: false,
          status: 0,
          body: err instanceof Error ? err.message : "Unknown network error",
        });
      }
    }

    setResults(next);
    setLoading(false);
  };

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold">Network Debug</h1>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
        Use this page from any device to verify browser {"->"} frontend {"->"} backend routing.
      </p>

      <div className="mt-4 rounded-lg border border-gray-200 p-4 text-sm dark:border-gray-700">
        <p><strong>Browser origin:</strong> {origin || "(loading...)"}</p>
        <p><strong>API base used by app:</strong> {apiBase}</p>
      </div>

      <button
        onClick={runChecks}
        disabled={loading}
        className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Running checks..." : "Run checks"}
      </button>

      <div className="mt-4 space-y-3">
        {results.map((result) => (
          <div key={result.url} className="rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700">
            <p className="font-medium break-all">{result.url}</p>
            <p className={result.ok ? "text-green-600" : "text-red-600"}>
              status={result.status}
            </p>
            <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-2 text-xs dark:bg-gray-900">
              {result.body || "(empty body)"}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
