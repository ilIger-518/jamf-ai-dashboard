"use client";

import {
  ArrowDownToLine,
  ArrowRightLeft,
  CheckCircle2,
  ExternalLink,
  FileCode2,
  FolderSync,
  HardDrive,
  RefreshCw,
  Shield,
  Terminal,
} from "lucide-react";

const FEATURES = [
  {
    icon: ArrowRightLeft,
    title: "Multi-server transfers",
    description:
      "Move packages between multiple Jamf Pro servers — e.g. from a test environment to production.",
  },
  {
    icon: FolderSync,
    title: "Flexible distribution points",
    description:
      "Copy files between Cloud DPs, file share DPs, or local file folders treated as distribution points.",
  },
  {
    icon: RefreshCw,
    title: "Automatic checksums",
    description:
      "Checksums are created and verified automatically so only changed packages are transferred.",
  },
  {
    icon: HardDrive,
    title: "Local folder support",
    description:
      "Treat any local folder as a distribution point to upload or download multiple packages at once.",
  },
  {
    icon: Shield,
    title: "Secure credential storage",
    description:
      "Jamf Pro and file share DP credentials are stored securely in the macOS Keychain.",
  },
  {
    icon: Terminal,
    title: "Command line interface",
    description:
      "Script and automate synchronisations with built-in CLI parameters — no GUI required.",
  },
];

const QUICK_STEPS = [
  "Download the latest release from GitHub.",
  'Open "Jamf Sync.app" and go to Settings.',
  "Add your Jamf Pro servers and/or local folders.",
  "Choose a source and a destination distribution point.",
  'Click Synchronize (or use the CLI with "JamfSync --srcDp … --dstDp …").',
];

export default function JamfSyncPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Jamf Sync</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            A macOS utility for transferring packages between Jamf Pro distribution points.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a
            href="https://github.com/jamf/JamfSync/releases/latest"
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition"
          >
            <ArrowDownToLine className="h-4 w-4" />
            Download
          </a>
          <a
            href="https://github.com/jamf/JamfSync"
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800 transition"
          >
            <ExternalLink className="h-4 w-4" />
            GitHub
          </a>
        </div>
      </div>

      {/* About card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          About
        </h2>
        <p className="text-sm leading-relaxed text-gray-700 dark:text-gray-300">
          Jamf Sync is an open-source macOS application maintained by Jamf. It simplifies the
          synchronisation of packages and files across Jamf Pro file share distribution points,
          JDCS2 (Cloud DP) distribution points, and local file folders. It can also keep the
          package list on a Jamf Pro server in sync with your chosen source distribution point,
          removing stale entries automatically.
        </p>
      </div>

      {/* Features grid */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Features
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
            >
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-950">
                <Icon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">{title}</h3>
              <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                {description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Quick start */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Quick Start
        </h2>
        <ol className="space-y-2">
          {QUICK_STEPS.map((step, index) => (
            <li key={index} className="flex items-start gap-3 text-sm text-gray-700 dark:text-gray-300">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* CLI reference */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <div className="mb-3 flex items-center gap-2">
          <FileCode2 className="h-4 w-4 text-gray-500" />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            CLI Reference
          </h2>
        </div>
        <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
          Run the app at least once to configure servers before using the CLI.
        </p>
        <pre className="overflow-x-auto rounded-lg bg-gray-900 p-4 text-xs leading-relaxed text-gray-100">
          {`JamfSync [-s | --srcDp <name>] [-d | --dstDp <name>]
         [-f | --forceSync] [-r | --removeFilesNotOnSource]
         [-rp | --removePackagesNotOnSource] [-p | --progress]
JamfSync [-h | --help]
JamfSync [-v | --version]`}
        </pre>
        <div className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
          {[
            { flag: "-s / --srcDp", desc: "Name of the source distribution point" },
            { flag: "-d / --dstDp", desc: "Name of the destination distribution point" },
            { flag: "-f / --forceSync", desc: "Copy all files even when checksums match" },
            { flag: "-r / --removeFilesNotOnSource", desc: "Delete files on destination not on source" },
            { flag: "-rp / --removePackagesNotOnSource", desc: "Remove Jamf Pro packages not on source" },
            { flag: "-p / --progress", desc: "Show progress during synchronisation" },
          ].map(({ flag, desc }) => (
            <div
              key={flag}
              className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/60"
            >
              <p className="font-mono font-semibold text-gray-800 dark:text-gray-200">{flag}</p>
              <p className="mt-0.5 text-gray-500 dark:text-gray-400">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Links */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Resources
        </h2>
        <div className="flex flex-wrap gap-3">
          {[
            { label: "GitHub Repository", href: "https://github.com/jamf/JamfSync" },
            {
              label: "Latest Release",
              href: "https://github.com/jamf/JamfSync/releases/latest",
            },
            {
              label: "User Guide (PDF)",
              href: "https://github.com/jamf/JamfSync/blob/main/JamfSync/Resources/Jamf%20Sync%20User%20Guide.pdf",
            },
            { label: "Report an Issue", href: "https://github.com/jamf/JamfSync/issues" },
          ].map(({ label, href }) => (
            <a
              key={label}
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 transition"
            >
              {label}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
