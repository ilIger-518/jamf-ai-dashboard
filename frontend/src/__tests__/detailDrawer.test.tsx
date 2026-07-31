import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DetailDrawer, DrawerRow, DrawerSection } from "@/components/shared/DetailDrawer";

describe("DetailDrawer", () => {
  it("renders its title and closes on request", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <DetailDrawer open={true} onClose={onClose} title="Device details">
        <DrawerSection title="Identity">
          <DrawerRow label="Name" value="MacBook" />
        </DrawerSection>
      </DetailDrawer>,
    );

    expect(screen.getByText("Device details")).toBeTruthy();
    expect(screen.getByText("MacBook")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
