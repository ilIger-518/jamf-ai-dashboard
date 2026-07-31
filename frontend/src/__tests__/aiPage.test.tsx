import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiAssistantPage from "@/app/(dashboard)/ai/page";

const fetchMock = vi.fn();

const { mockUseQuery, mockUseMutation, mockInvalidateQueries, mockSetQueryData, mockUseAuthStore, mockToastSuccess, mockToastError } = vi.hoisted(() => ({
  mockUseQuery: vi.fn(),
  mockUseMutation: vi.fn(),
  mockInvalidateQueries: vi.fn(),
  mockSetQueryData: vi.fn(),
  mockUseAuthStore: vi.fn(),
  mockToastSuccess: vi.fn(),
  mockToastError: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: mockUseQuery,
  useMutation: mockUseMutation,
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
    setQueryData: mockSetQueryData,
  }),
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: mockUseAuthStore,
}));

vi.mock("sonner", () => ({
  toast: {
    success: mockToastSuccess,
    error: mockToastError,
  },
}));

describe("AiAssistantPage", () => {
  beforeEach(() => {
    mockUseQuery.mockReset();
    mockUseMutation.mockReset();
    mockInvalidateQueries.mockReset();
    mockSetQueryData.mockReset();
    mockUseAuthStore.mockReset();
    mockToastSuccess.mockReset();
    mockToastError.mockReset();

    mockUseQuery.mockImplementation((options: { queryKey?: unknown[] }) => {
      const key = options.queryKey?.[0];
      if (key === "ai-sessions") return { data: [] };
      if (key === "servers") return { data: [{ id: "srv-1", name: "Primary", is_active: true }] };
      if (key === "knowledge-bases") return { data: [] };
      return { data: [] };
    });
    mockUseMutation.mockReturnValue({ mutate: vi.fn() });
    mockUseAuthStore.mockImplementation((selector: (state: { accessToken: string | null }) => string | null) => selector({ accessToken: "token-1" }));
    fetchMock.mockReset();
  });

  it("allows sending a message from the input field", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('{"type":"final","session_id":"s1","reply":"Hello there","sources":[]}\n') })
            .mockResolvedValueOnce({ done: true, value: undefined }),
        }),
      },
      headers: new Headers(),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AiAssistantPage />);

    await user.type(screen.getByPlaceholderText(/ask about your jamf environment/i), "Hello");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(fetchMock).toHaveBeenCalled();
  });
});
