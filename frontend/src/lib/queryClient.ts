import { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AxiosError } from "axios";

function getErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: string })?.detail;
    if (detail) return detail;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      gcTime: 1000 * 60 * 5, // 5 minutes
      retry: (failureCount, error) => {
        if (error instanceof AxiosError && error.response?.status === 401) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      onError: (error) => {
        toast.error(getErrorMessage(error));
      },
    },
  },
});
