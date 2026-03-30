"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Eye, Loader2, RefreshCw, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface KnowledgeSource {
  id: string;
  title: string;
  source: string;
  doc_type: string;
  chunk_count: number;
  size_bytes: number;
  knowledge_base_id: string | null;
  knowledge_base_name: string | null;
  knowledge_base_dimension_tag: string | null;
  ingested_at: string;
}

interface SourcePreview {
  source_id: string;
  title: string;
  source: string;
  doc_type: string;
  chunk_count: number;
  size_bytes: number;
  knowledge_base_name: string | null;
  preview_text: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
}

function SourcePreviewModal({ source, onClose }: { source: KnowledgeSource; onClose: () => void }) {
  const { data, isLoading, isFetching } = useQuery<SourcePreview>({
    queryKey: ["knowledge-source-preview", source.id],
    queryFn: () => api.get<SourcePreview>(`/knowledge/sources/${source.id}/preview`).then((r) => r.data),
    staleTime: 60_000,
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-4xl rounded-2xl bg-white p-4 shadow-2xl dark:bg-gray-900">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Readable Source Preview</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{source.title}</p>
          </div>
          <div className="flex items-center gap-2">
            {isFetching && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
            <button onClick={onClose} className="rounded p-1 hover:bg-gray-100 dark:hover:bg-gray-800">
              <X className="h-4 w-4 text-gray-400" />
            </button>
          </div>
        </div>

        <div className="mb-3 rounded-lg border border-gray-200 bg-gray-50 p-2 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800/60 dark:text-gray-300">
          <div className="truncate">Source: {source.source}</div>
          <div className="mt-1">Chunks: {source.chunk_count} • Size: {formatBytes(source.size_bytes)}</div>
        </div>

        <div className="h-[60vh] overflow-y-auto rounded-lg border border-gray-200 bg-white p-4 text-sm leading-relaxed text-gray-800 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-gray-400">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : (
            <pre className="whitespace-pre-wrap font-sans">{data?.preview_text || "No preview available."}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

export default function KnowledgeSourcesPage() {
  const qc = useQueryClient();
  const [sourceSearch, setSourceSearch] = useState("");
  const [previewSource, setPreviewSource] = useState<KnowledgeSource | null>(null);

  const { data: sources = [], isLoading: sourcesLoading } = useQuery<KnowledgeSource[]>({
    queryKey: ["knowledge-sources"],
    queryFn: () => api.get<KnowledgeSource[]>("/knowledge/sources").then((r) => r.data),
  });

  const deleteSource = useMutation({
    mutationFn: (id: string) => api.delete(`/knowledge/sources/${id}`),
    onSuccess: () => {
      toast.success("Source deleted");
      qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
    onError: () => toast.error("Failed to delete source"),
  });

  const filteredSources = useMemo(() => {
    const q = sourceSearch.trim().toLowerCase();
    if (!q) return sources;
    return sources.filter((s) => {
      return (
        s.title.toLowerCase().includes(q) ||
        s.source.toLowerCase().includes(q) ||
        (s.knowledge_base_name || "").toLowerCase().includes(q)
      );
    });
  }, [sourceSearch, sources]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Stored Sources</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Browse and manage ingested documents separately from live scrape jobs.
          </p>
        </div>
        <Link
          href="/knowledge"
          className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
        >
          <BookOpen className="h-4 w-4" />
          Back to Knowledge
        </Link>
      </div>

      {previewSource && <SourcePreviewModal source={previewSource} onClose={() => setPreviewSource(null)} />}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="border-b border-gray-200 p-3 dark:border-gray-700">
          <input
            value={sourceSearch}
            onChange={(e) => setSourceSearch(e.target.value)}
            placeholder="Search sources by title, URL, or knowledge base..."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
        </div>

        {sourcesLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : filteredSources.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
            <BookOpen className="h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {sources.length === 0
                ? "No documents ingested yet. Run a scrape job to populate the knowledge base."
                : "No sources match your search."}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
              <tr>
                {["Title", "URL", "Knowledge Base", "Chunks", "Size", "Ingested", "", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {filteredSources.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="max-w-xs truncate px-4 py-3 font-medium text-gray-900 dark:text-white" title={s.title}>
                    {s.title}
                  </td>
                  <td className="max-w-xs truncate px-4 py-3 text-xs text-blue-600 dark:text-blue-400" title={s.source}>
                    <a href={s.source} target="_blank" rel="noreferrer noopener" className="hover:underline">
                      {s.source.replace(/^https?:\/\//, "").slice(0, 60)}
                      {s.source.length > 67 ? "..." : ""}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                    {s.knowledge_base_name || "Default"}
                    {s.knowledge_base_dimension_tag ? ` (${s.knowledge_base_dimension_tag})` : ""}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{s.chunk_count}</td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{formatBytes(s.size_bytes)}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">{new Date(s.ingested_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setPreviewSource(s)}
                      className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Preview
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => {
                        if (confirm(`Delete \"${s.title}\" from the knowledge base?`)) {
                          deleteSource.mutate(s.id);
                        }
                      }}
                      className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
                      title="Delete source"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
