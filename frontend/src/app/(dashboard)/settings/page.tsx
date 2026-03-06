"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Trash2, RefreshCw, CheckCircle, XCircle, Pencil, Server } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface JamfServer {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
  last_sync: string | null;
  last_sync_error: string | null;
  created_at: string;
}

interface ServerFormValues {
  name: string;
  url: string;
  client_id: string;
  client_secret: string;
  ai_client_id: string;
  ai_client_secret: string;
}

const emptyForm: ServerFormValues = {
  name: "",
  url: "",
  client_id: "",
  client_secret: "",
  ai_client_id: "",
  ai_client_secret: "",
};

function ServerModal({
  initial,
  onClose,
  onSave,
  saving,
}: {
  initial?: JamfServer | null;
  onClose: () => void;
  onSave: (v: ServerFormValues) => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<ServerFormValues>(
    initial
      ? { name: initial.name, url: initial.url, client_id: "", client_secret: "", ai_client_id: "", ai_client_secret: "" }
      : emptyForm
  );

  const field = (key: keyof ServerFormValues, label: string, placeholder: string, type = "text") => (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      <input
        type={type}
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {initial ? "Edit Jamf Server" : "Add Jamf Server"}
        </h2>
        <div className="space-y-3">
          {field("name", "Name", "My Jamf Pro")}
          {field("url", "Jamf Pro URL", "https://yourinstance.jamfcloud.com")}
          <hr className="border-gray-200 dark:border-gray-700" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            API Role credentials with read access
          </p>
          {field("client_id", "Client ID", "API client ID")}
          {field("client_secret", "Client Secret", "API client secret", "password")}
          <hr className="border-gray-200 dark:border-gray-700" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Optional: dedicated read-only credentials for the AI module
          </p>
          {field("ai_client_id", "AI Client ID (optional)", "")}
          {field("ai_client_secret", "AI Client Secret (optional)", "", "password")}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(form)}
            disabled={saving || !form.name || !form.url || (!initial && (!form.client_id || !form.client_secret))}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : initial ? "Save Changes" : "Add Server"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const [modal, setModal] = useState<"add" | JamfServer | null>(null);

  const { data: servers = [], isLoading } = useQuery<JamfServer[]>({
    queryKey: ["servers"],
    queryFn: () => api.get<JamfServer[]>("/servers").then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (body: ServerFormValues) => api.post("/servers", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server added"); setModal(null); },
    onError: () => toast.error("Failed to add server"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ServerFormValues> }) =>
      api.patch(`/servers/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server updated"); setModal(null); },
    onError: () => toast.error("Failed to update server"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/servers/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); toast.success("Server removed"); },
    onError: () => toast.error("Failed to delete server"),
  });

  const handleSave = (form: ServerFormValues) => {
    if (modal === "add") {
      createMutation.mutate(form);
    } else if (modal && typeof modal === "object") {
      const patch: Partial<ServerFormValues> = {};
      if (form.name !== modal.name) patch.name = form.name;
      if (form.url !== modal.url) patch.url = form.url;
      if (form.client_id) patch.client_id = form.client_id;
      if (form.client_secret) patch.client_secret = form.client_secret;
      if (form.ai_client_id) patch.ai_client_id = form.ai_client_id;
      if (form.ai_client_secret) patch.ai_client_secret = form.ai_client_secret;
      updateMutation.mutate({ id: modal.id, body: patch });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Settings</h1>
        <button
          onClick={() => setModal("add")}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add Jamf Server
        </button>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Jamf Pro Connections
          </h2>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : servers.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <Server className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No Jamf servers connected yet. Add one to start syncing data.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {servers.map((s) => (
              <li key={s.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  {s.is_active ? (
                    <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
                  ) : (
                    <XCircle className="h-4 w-4 shrink-0 text-gray-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{s.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{s.url}</p>
                    {s.last_sync_error && (
                      <p className="mt-0.5 text-xs text-red-500 dark:text-red-400">
                        {s.last_sync_error}
                      </p>
                    )}
                    {s.last_sync && !s.last_sync_error && (
                      <p className="mt-0.5 text-xs text-gray-400">
                        Last sync: {new Date(s.last_sync).toLocaleString()}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setModal(s)}
                    className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Remove "${s.name}"?`)) deleteMutation.mutate(s.id);
                    }}
                    className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {modal && (
        <ServerModal
          initial={modal === "add" ? null : modal}
          onClose={() => setModal(null)}
          onSave={handleSave}
          saving={createMutation.isPending || updateMutation.isPending}
        />
      )}
    </div>
  );
}
