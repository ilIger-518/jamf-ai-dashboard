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
  const { accessToken, user, isLoading, fetchMe } = useAuthStore();

  useEffect(() => {
    if (!accessToken) {
      router.replace("/login");
      return;
    }
    if (!user && !isLoading) {
      fetchMe();
    }
  }, [accessToken, user, isLoading, fetchMe, router]);

  useEffect(() => {
    if (adminOnly && user && !user.is_admin) {
      router.replace("/");
    }
  }, [adminOnly, user, router]);

  return { user, isLoading };
}
