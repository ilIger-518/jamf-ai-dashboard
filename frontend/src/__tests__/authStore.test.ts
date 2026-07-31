import { beforeEach, describe, expect, it, vi } from "vitest";

const mockApi = {
  post: vi.fn(),
  get: vi.fn(),
};

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

describe("auth store", () => {
  beforeEach(() => {
    vi.resetModules();
    mockApi.post.mockReset();
    mockApi.get.mockReset();
  });

  it("logs in and fetches the current user", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { access_token: "token-123" } });
    mockApi.get.mockResolvedValueOnce({ data: { id: "1", username: "demo", email: "demo@example.com", is_admin: false, permissions: [] } });

    const { useAuthStore } = await import("@/store/authStore");
    const store = useAuthStore.getState();

    await store.login("demo", "secret");

    expect(mockApi.post).toHaveBeenCalledWith("/auth/login", {
      username: "demo",
      password: "secret",
    });
    expect(mockApi.get).toHaveBeenCalledWith("/auth/me");
    expect(useAuthStore.getState().accessToken).toBe("token-123");
    expect(useAuthStore.getState().user?.username).toBe("demo");
  });

  it("clears auth state on failed fetchMe", async () => {
    mockApi.get.mockRejectedValueOnce(new Error("boom"));

    const { useAuthStore } = await import("@/store/authStore");
    const store = useAuthStore.getState();

    await store.fetchMe();

    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().hasHydrated).toBe(true);
  });
});
