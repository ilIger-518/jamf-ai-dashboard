import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

const mockPost = vi.fn();
const mockGetState = vi.fn();

vi.mock("@/store/authStore", () => ({
  useAuthStore: {
    getState: mockGetState,
  },
}));

describe("api client", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGetState.mockReset();
    mockGetState.mockReturnValue({ accessToken: "token-1" });
    vi.resetModules();
  });

  it("adds the access token header when present", async () => {
    const { api: client } = await import("@/lib/api");

    const requestConfig = await client.interceptors.request.handlers[0].fulfilled({ headers: {} });

    expect(requestConfig.headers.Authorization).toBe("Bearer token-1");
  });
});
