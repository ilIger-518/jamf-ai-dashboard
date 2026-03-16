"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading, accessToken, hasHydrated } = useAuthStore();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  // Only redirect away from login once we know for sure the user is authenticated.
  useEffect(() => {
    if (hasHydrated && accessToken) {
      router.replace("/");
    }
  }, [accessToken, hasHydrated, router]);

  const onSubmit = async (values: LoginFormValues) => {
    try {
      await login(values.username, values.password);
      // hasHydrated will be true after login, the effect above handles the redirect.
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        toast.error("Invalid username or password");
      } else {
        toast.error("Cannot reach API server. Use this server's IP and ensure backend is reachable on port 8000.");
      }
    }
  };

  const microsoftSsoUrl = `${API_BASE_URL}/api/v1/auth/sso/microsoft/start`;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-lg dark:bg-gray-900">
        {/* Logo / heading */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-white font-bold text-xl">
            J
          </div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Jamf AI Dashboard
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Sign in to your account
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
          <div>
            <label
              htmlFor="username"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              {...register("username")}
              className={cn(
                "block w-full rounded-lg border px-3 py-2 text-sm shadow-sm outline-none",
                "bg-white dark:bg-gray-800 text-gray-900 dark:text-white",
                "transition focus:ring-2 focus:ring-blue-500",
                errors.username
                  ? "border-red-500 focus:ring-red-500"
                  : "border-gray-300 dark:border-gray-600",
              )}
            />
            {errors.username && (
              <p className="mt-1 text-xs text-red-600">{errors.username.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
              className={cn(
                "block w-full rounded-lg border px-3 py-2 text-sm shadow-sm outline-none",
                "bg-white dark:bg-gray-800 text-gray-900 dark:text-white",
                "transition focus:ring-2 focus:ring-blue-500",
                errors.password
                  ? "border-red-500 focus:ring-red-500"
                  : "border-gray-300 dark:border-gray-600",
              )}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className={cn(
              "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5",
              "bg-blue-600 text-sm font-medium text-white shadow-sm",
              "hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2",
              "disabled:cursor-not-allowed disabled:opacity-60 transition",
            )}
          >
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
            {isLoading ? "Signing in…" : "Sign in"}
          </button>

          <div className="relative py-1">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200 dark:border-gray-700" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-2 text-gray-400 dark:bg-gray-900">or</span>
            </div>
          </div>

          <a
            href={microsoftSsoUrl}
            className="flex w-full items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            Sign in with Microsoft
          </a>
        </form>
      </div>
    </div>
  );
}
