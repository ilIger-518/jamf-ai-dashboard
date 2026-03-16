"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

export default function SsoCallbackPage() {
  const router = useRouter();
  const { initialize } = useAuthStore();

  useEffect(() => {
    const run = async () => {
      const status = new URLSearchParams(window.location.search).get("status");
      if (status !== "success") {
        router.replace("/login");
        return;
      }
      await initialize();
      if (useAuthStore.getState().accessToken) {
        router.replace("/");
        return;
      }
      router.replace("/login?sso_error=session_init_failed");
    };

    void run();
  }, [initialize, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
        <Loader2 className="h-4 w-4 animate-spin" />
        Signing you in with Microsoft...
      </div>
    </div>
  );
}
