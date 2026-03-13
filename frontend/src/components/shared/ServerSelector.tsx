"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Server, Check } from "lucide-react";
import { api } from "@/lib/api";
import { useUiStore } from "@/store/uiStore";
import { cn } from "@/lib/utils";

interface JamfServer {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
}

export function ServerSelector({ collapsed = false }: { collapsed?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { selectedServerId, setSelectedServer } = useUiStore();

  const { data: servers = [] } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
    staleTime: 60_000,
  });

  const selected = servers.find((s) => s.id === selectedServerId) ?? null;

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (collapsed) {
    return (
      <div className="flex justify-center py-2">
        <button
          title={selected?.name ?? "All Servers"}
          onClick={() => setOpen((v) => !v)}
          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
        >
          <Server className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 transition"
      >
        <span className="flex items-center gap-2 min-w-0">
          <Server className="h-4 w-4 shrink-0 text-gray-400" />
          <span className="truncate font-medium text-gray-700 dark:text-gray-200">
            {selected ? selected.name : "All Servers"}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform duration-150",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-900">
          {/* All Servers */}
          <button
            onClick={() => { setSelectedServer(null); setOpen(false); }}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            <span className="font-medium text-gray-700 dark:text-gray-200">All Servers</span>
            {!selectedServerId && <Check className="h-3.5 w-3.5 text-blue-500" />}
          </button>

          {servers.length > 0 && (
            <div className="my-1 border-t border-gray-100 dark:border-gray-800" />
          )}

          {servers.map((server) => (
            <button
              key={server.id}
              onClick={() => { setSelectedServer(server.id); setOpen(false); }}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 transition"
            >
              <span className="flex flex-col items-start min-w-0">
                <span className={cn("truncate font-medium", selectedServerId === server.id ? "text-blue-600 dark:text-blue-400" : "text-gray-700 dark:text-gray-200")}>
                  {server.name}
                </span>
                {!server.is_active && (
                  <span className="text-xs text-red-500">inactive</span>
                )}
              </span>
              {selectedServerId === server.id && (
                <Check className="h-3.5 w-3.5 shrink-0 text-blue-500" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
