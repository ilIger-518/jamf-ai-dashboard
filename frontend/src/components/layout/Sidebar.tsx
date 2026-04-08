"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Monitor,
  Shield,
  Users,
  Package,
  ClipboardCheck,
  Bot,
  BookOpen,
  FileCode2,
  Box,
  Settings,
  ArrowRightLeft,
  ChevronLeft,
  ChevronRight,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/uiStore";
import { ServerSelector } from "@/components/shared/ServerSelector";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/devices", label: "Devices", icon: Monitor },
  { href: "/policies", label: "Policies", icon: Shield },
  { href: "/smart-groups", label: "Smart Groups", icon: Users },
  { href: "/patches", label: "Patches", icon: Package },
  { href: "/compliance", label: "Compliance", icon: ClipboardCheck },
  { href: "/ddm", label: "DDM Status", icon: Layers },
  { href: "/ai", label: "AI Assistant", icon: Bot },
  { href: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { href: "/scripts", label: "Scripts", icon: FileCode2 },
  { href: "/packages", label: "Packages", icon: Box },
  { href: "/migrator", label: "Migrator", icon: ArrowRightLeft },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useUiStore();

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-gray-200 dark:border-gray-800",
        "bg-white dark:bg-gray-900 transition-all duration-200",
        sidebarCollapsed ? "w-16" : "w-60",
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "flex h-14 items-center border-b border-gray-200 dark:border-gray-800 px-4",
          sidebarCollapsed ? "justify-center" : "justify-between",
        )}
      >
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">
            Jamf Dashboard
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Server Selector */}
      <div className="border-b border-gray-200 dark:border-gray-800 px-2 py-2">
        <ServerSelector collapsed={sidebarCollapsed} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                  : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800",
                sidebarCollapsed && "justify-center px-2",
              )}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!sidebarCollapsed && <span>{label}</span>}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
