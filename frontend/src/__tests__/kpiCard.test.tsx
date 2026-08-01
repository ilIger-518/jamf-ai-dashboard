import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { Monitor } from "lucide-react";

describe("KpiCard", () => {
  it("renders the provided label, value, and subtitle", () => {
    render(
      <KpiCard
        label="Total Devices"
        value={42}
        sub="24 managed"
        icon={Monitor}
        color="bg-blue-50"
      />,
    );

    expect(screen.getByText("Total Devices")).toBeTruthy();
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("24 managed")).toBeTruthy();
  });

  it("highlights alert values when the card is marked as alerting", () => {
    render(
      <KpiCard
        label="Non-Compliant"
        value={7}
        sub="Needs review"
        icon={Monitor}
        color="bg-red-50"
        alert
      />,
    );

    expect(screen.getByText("Non-Compliant")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("Needs review")).toBeTruthy();
  });
});
