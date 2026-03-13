import { create } from "zustand";
import { api } from "@/lib/api";

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
  is_active?: boolean;
  role_id?: string | null;
  role_name?: string | null;
  permissions: string[];
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  isLoading: boolean;
  hasHydrated: boolean;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  initialize: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  isLoading: false,
  hasHydrated: false,

  setAccessToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),

  /**
   * Called once on app mount to restore a session from the refresh-token cookie.
   * Sets hasHydrated=true when complete (whether or not the session was restored).
   */
  initialize: async () => {
    if (get().hasHydrated) return;
    try {
      // The httpOnly refresh-token cookie is sent automatically via withCredentials.
      const { data } = await api.post<{ access_token: string }>("/auth/refresh", {});
      set({ accessToken: data.access_token });
      const { data: me } = await api.get<AuthUser>("/auth/me");
      set({ user: me, hasHydrated: true });
    } catch {
      // No valid session — land on login page.
      set({ accessToken: null, user: null, hasHydrated: true });
    }
  },

  login: async (username, password) => {
    set({ isLoading: true });
    try {
      const { data } = await api.post<{ access_token: string }>("/auth/login", {
        username,
        password,
      });
      set({ accessToken: data.access_token });
      // Backend /login returns only a token; fetch the profile separately.
      const { data: me } = await api.get<AuthUser>("/auth/me");
      set({ user: me, hasHydrated: true });
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
      set({ accessToken: null, user: null, hasHydrated: true });
    }
  },

  fetchMe: async () => {
    set({ isLoading: true });
    try {
      const { data } = await api.get<AuthUser>("/auth/me");
      set({ user: data, hasHydrated: true });
    } catch {
      set({ accessToken: null, user: null, hasHydrated: true });
    } finally {
      set({ isLoading: false });
    }
  },
}));
