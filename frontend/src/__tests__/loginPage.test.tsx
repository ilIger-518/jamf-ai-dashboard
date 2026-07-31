import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/(auth)/login/page";

const { mockLogin, mockUseAuthStore } = vi.hoisted(() => ({
  mockLogin: vi.fn(),
  mockUseAuthStore: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn() },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: mockUseAuthStore,
}));

describe("LoginPage", () => {
  beforeEach(() => {
    mockLogin.mockReset();
    mockUseAuthStore.mockReset();
    mockUseAuthStore.mockReturnValue({
      login: mockLogin,
      isLoading: false,
      accessToken: null,
      hasHydrated: true,
    });
  });

  it("submits credentials to the auth store", async () => {
    mockLogin.mockResolvedValue(undefined);

    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/username/i), "demo");
    await user.type(screen.getByLabelText(/password/i), "super-secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("demo", "super-secret");
    });
  });

  it("shows validation errors for missing fields", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(screen.getByText("Username is required")).toBeTruthy();
    expect(screen.getByText("Password is required")).toBeTruthy();
    expect(mockLogin).not.toHaveBeenCalled();
  });
});
