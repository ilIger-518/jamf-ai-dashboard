"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

/**
 * Redirects to /login if unauthenticated.
 * Optionally restricts to admins only.
 */
export function useRequireAuth({ adminOnly = false } = {}) {
  const router = useRouter();
  const { accessToken, user, isLoading, hasHydrated, fetchMe, initialize } = useAuthStore();

  useEffect(() => {
    if (!hasHydrated) {
      // First mount: try to restore the session from the refresh-token cookie.
      // initialize() will set hasHydrated=true when done, re-triggering this effect.
      initialize();
      return;
    }

    if (!accessToken) {
      router.replace("/login");
      return;
    }
    if (!user && !isLoading) {
      fetchMe();
    }
  }, [accessToken, user, isLoading, hasHydrated, fetchMe, initialize, router]);

  useEffect(() => {
    if (adminOnly && user && !user.is_admin) {
      router.replace("/");
    }
  }, [adminOnly, user, router]);

  // Show spinner while restoring session OR while a fetch is in-flight.
  return { user, isLoading: isLoading || !hasHydrated };
}
