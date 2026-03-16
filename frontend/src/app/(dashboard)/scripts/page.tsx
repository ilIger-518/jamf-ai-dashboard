"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileCode2, Loader2 } from "lucide-react";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/uiStore";

const SyntaxHighlighter = dynamic(
  () => import("react-syntax-highlighter").then((mod) => mod.Prism),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[220px] items-center justify-center text-xs text-gray-400">
        Loading code viewer...
      </div>
    ),
  },
);

interface ScriptItem {
  id: number;
  name: string;
  category: string | null;
  jamf_script_url: string;
}

interface ScriptParameter {
  index: number;
  label: string;
  value: string;
}

interface ScriptDetailItem {
  id: number;
  name: string;
  category: string | null;
  notes: string | null;
  info: string | null;
  priority: string | null;
  os_requirements: string | null;
  script_contents: string;
  parameters: ScriptParameter[];
  jamf_script_url: string;
}

type ScriptLanguage =
  | "bash"
  | "python"
  | "powershell"
  | "javascript"
  | "typescript"
  | "ruby"
  | "swift"
  | "plaintext";

const LANGUAGE_OPTIONS: Array<{ value: ScriptLanguage; label: string }> = [
  { value: "bash", label: "Bash / Shell" },
  { value: "python", label: "Python" },
  { value: "powershell", label: "PowerShell" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "ruby", label: "Ruby" },
  { value: "swift", label: "Swift" },
  { value: "plaintext", label: "Plain Text" },
];

const LARGE_SCRIPT_THRESHOLD = 12000;

function detectLanguage(scriptContents: string): ScriptLanguage {
  const text = scriptContents.trim();
  const firstLine = text.split("\n", 1)[0]?.toLowerCase() ?? "";
  if (firstLine.includes("python")) return "python";
  if (firstLine.includes("powershell") || firstLine.includes("pwsh")) return "powershell";
  if (firstLine.includes("bash") || firstLine.includes("sh") || firstLine.startsWith("#!")) {
    return "bash";
  }
  if (text.includes("function ") || text.includes("const ") || text.includes("let ")) {
    return "javascript";
  }
  if (text.includes(": string") || text.includes("interface ")) return "typescript";
  if (text.includes("end") && text.includes("def ")) return "ruby";
  if (text.includes("import Foundation") || text.includes("func ")) return "swift";
  return "plaintext";
}

export default function ScriptsPage() {
  const { selectedServerId } = useUiStore();
  const [selectedScriptId, setSelectedScriptId] = useState<number | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<ScriptLanguage>("bash");
  const [highlightEnabled, setHighlightEnabled] = useState(false);

  const { data = [], isLoading: isLoadingScripts } = useQuery<ScriptItem[]>({
    queryKey: ["assets", "scripts", selectedServerId],
    enabled: !!selectedServerId,
    queryFn: () =>
      api
        .get<ScriptItem[]>("/assets/scripts", { params: { server_id: selectedServerId } })
        .then((r) => r.data),
  });

  useEffect(() => {
    setSelectedScriptId(null);
  }, [selectedServerId]);

  useEffect(() => {
    if (!data.length || selectedScriptId === null) {
      setSelectedScriptId(null);
      return;
    }
    if (!data.some((item) => item.id === selectedScriptId)) {
      setSelectedScriptId(null);
    }
  }, [data, selectedScriptId]);

  const {
    data: selectedScript,
    isLoading: isLoadingScriptDetail,
    isFetching: isFetchingScriptDetail,
  } = useQuery<ScriptDetailItem>({
    queryKey: ["assets", "script-detail", selectedServerId, selectedScriptId],
    enabled: !!selectedServerId && selectedScriptId !== null,
    queryFn: () =>
      api
        .get<ScriptDetailItem>(`/assets/scripts/${selectedScriptId}`, {
          params: { server_id: selectedServerId },
        })
        .then((r) => r.data),
  });

  useEffect(() => {
    if (!selectedScript) return;
    setSelectedLanguage(detectLanguage(selectedScript.script_contents));
    setHighlightEnabled((selectedScript.script_contents?.length ?? 0) <= LARGE_SCRIPT_THRESHOLD);
  }, [selectedScript]);

  const scriptCountLabel = useMemo(() => `${data.length.toLocaleString()} total`, [data.length]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Scripts</h1>
        <span className="text-sm text-gray-500">{scriptCountLabel}</span>
      </div>

      {!selectedServerId ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
          Select a server from the top-left server selector to view scripts.
        </div>
      ) : isLoadingScripts ? (
        <div className="flex items-center justify-center rounded-xl border border-gray-200 bg-white py-16 dark:border-gray-700 dark:bg-gray-900">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center dark:border-gray-700 dark:bg-gray-900">
          <FileCode2 className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No scripts found on this Jamf server.</p>
        </div>
      ) : (
        <div
          className={cn(
            "grid gap-4",
            selectedScriptId === null ? "grid-cols-1" : "xl:grid-cols-[0.44fr_0.56fr]",
          )}
        >
          <div className="min-w-0 overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                    ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                    Category
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {data.map((s) => (
                  <tr
                    key={s.id}
                    className={cn(
                      "align-top",
                      selectedScriptId === s.id
                        ? "bg-blue-50/70 dark:bg-blue-900/20"
                        : "hover:bg-gray-50 dark:hover:bg-gray-800/40",
                    )}
                  >
                    <td className="px-4 py-3">
                      <a
                        href={s.jamf_script_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 font-medium text-blue-600 hover:underline dark:text-blue-400"
                        title="Open in Jamf Pro"
                      >
                        {s.id}
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setSelectedScriptId(s.id)}
                        className="text-left font-medium text-gray-900 hover:text-blue-700 dark:text-white dark:hover:text-blue-300"
                      >
                        {s.name}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{s.category || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedScriptId !== null && (
          <div className="min-w-0 space-y-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
            {isLoadingScriptDetail ? (
              <div className="flex min-h-[380px] items-center justify-center rounded-lg border border-gray-200 dark:border-gray-700">
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              </div>
            ) : !selectedScript ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-300">
                Failed to load script details.
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {selectedScript.name}
                    </h2>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      ID {selectedScript.id} • {selectedScript.category || "No category"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setSelectedScriptId(null)}
                      className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                      Back to all scripts
                    </button>
                    <a
                      href={selectedScript.jamf_script_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 rounded-lg border border-blue-600 px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-900/20"
                    >
                      Open in Jamf Pro
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-800/60">
                    <p className="text-gray-400">Priority</p>
                    <p className="font-medium text-gray-700 dark:text-gray-200">{selectedScript.priority || "—"}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-800/60">
                    <p className="text-gray-400">OS Requirements</p>
                    <p className="font-medium text-gray-700 dark:text-gray-200">{selectedScript.os_requirements || "—"}</p>
                  </div>
                </div>

                {!!selectedScript.info && (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-800/60">
                    <p className="mb-1 text-gray-400">Info</p>
                    <p className="whitespace-pre-wrap text-gray-700 dark:text-gray-200">{selectedScript.info}</p>
                  </div>
                )}

                {!!selectedScript.notes && (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-800/60">
                    <p className="mb-1 text-gray-400">Notes</p>
                    <p className="whitespace-pre-wrap text-gray-700 dark:text-gray-200">{selectedScript.notes}</p>
                  </div>
                )}

                <div className="rounded-lg border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/60">
                    <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Script Contents</p>
                    <div className="flex items-center gap-2">
                      {isFetchingScriptDetail && <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />}
                      <select
                        value={selectedLanguage}
                        onChange={(e) => setSelectedLanguage(e.target.value as ScriptLanguage)}
                        className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300"
                      >
                        {LANGUAGE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => setHighlightEnabled((prev) => !prev)}
                        className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
                      >
                        {highlightEnabled ? "Disable highlight" : "Enable highlight"}
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[480px] max-w-full overflow-auto">
                    {!highlightEnabled ? (
                      <pre className="m-0 min-h-[220px] whitespace-pre-wrap break-words bg-[#111827] p-4 text-xs text-gray-100">
                        {selectedScript.script_contents || "# Empty script"}
                      </pre>
                    ) : (
                      <SyntaxHighlighter
                        language={selectedLanguage}
                        style={oneDark}
                        showLineNumbers={selectedScript.script_contents.length <= LARGE_SCRIPT_THRESHOLD}
                        wrapLongLines
                        customStyle={{
                          margin: 0,
                          fontSize: "0.78rem",
                          minHeight: "220px",
                          maxWidth: "100%",
                          overflowX: "auto",
                        }}
                      >
                        {selectedScript.script_contents || "# Empty script"}
                      </SyntaxHighlighter>
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-gray-200 dark:border-gray-700">
                  <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-800/60 dark:text-gray-300">
                    Script Parameters
                  </div>
                  {selectedScript.parameters.length === 0 ? (
                    <p className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">No parameters defined.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="border-b border-gray-100 text-gray-400 dark:border-gray-800">
                          <tr>
                            <th className="px-3 py-2 text-left">Parameter</th>
                            <th className="px-3 py-2 text-left">Value</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                          {selectedScript.parameters.map((parameter) => (
                            <tr key={`${parameter.index}-${parameter.value}`}>
                              <td className="whitespace-nowrap px-3 py-2 font-medium text-gray-700 dark:text-gray-200">
                                {parameter.label}
                              </td>
                              <td className="break-all px-3 py-2 font-mono text-gray-600 dark:text-gray-300">
                                {parameter.value}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
          )}
        </div>
      )}
    </div>
  );
}
