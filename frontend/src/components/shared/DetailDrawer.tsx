"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DetailDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function DetailDrawer({ open, onClose, title, children }: DetailDrawerProps) {
  return (
    <>
      {/* Overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity duration-300",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-2xl transition-transform duration-300 dark:bg-gray-900",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white truncate pr-4">{title}</h2>
          <button
            onClick={onClose}
            className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </>
  );
}

/** Labelled row inside a drawer section */
export function DrawerRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-h-[2rem] items-start gap-3 py-2">
      <span className="w-36 shrink-0 text-xs font-medium text-gray-500 dark:text-gray-400 leading-5">{label}</span>
      <span className="text-sm text-gray-900 dark:text-white leading-5 break-words min-w-0">{value ?? "—"}</span>
    </div>
  );
}

/** Titled section divider inside a drawer */
export function DrawerSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">{title}</p>
      <div className="divide-y divide-gray-100 dark:divide-gray-800">{children}</div>
    </div>
  );
}
