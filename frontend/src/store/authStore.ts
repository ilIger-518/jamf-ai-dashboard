import { create } from "zustand";
import { api } from "@/lib/api";

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  isLoading: boolean;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  isLoading: false,

  setAccessToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),

  login: async (username, password) => {
    set({ isLoading: true });
    try {
      const { data } = await api.post<{ access_token: string; user: AuthUser }>("/auth/login", {
        username,
        password,
      });
      set({ accessToken: data.access_token, user: data.user });
    } finally {
      set({ isLoading: false });
    }
  },

  logout: async () => {
    try {
      const token = get().accessToken;
      if (token) {
        await api.post("/auth/logout");
      }
    } catch {
      // ignore errors on logout
    } finally {
      set({ accessToken: null, user: null });
    }
  },

  fetchMe: async () => {
    set({ isLoading: true });
    try {
      const { data } = await api.get<AuthUser>("/auth/me");
      set({ user: data });
    } catch {
      set({ accessToken: null, user: null });
    } finally {
      set({ isLoading: false });
    }
  },
}));
