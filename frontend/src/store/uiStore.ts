import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  sidebarCollapsed: boolean;
  selectedServerId: string | null;
  theme: "light" | "dark" | "system";
  toggleSidebar: () => void;
  setSelectedServer: (id: string | null) => void;
  setTheme: (theme: "light" | "dark" | "system") => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      selectedServerId: null,
      theme: "system",

      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSelectedServer: (id) => set({ selectedServerId: id }),
      setTheme: (theme) => set({ theme }),
    }),
    { name: "jamf-dashboard-ui" },
  ),
);
