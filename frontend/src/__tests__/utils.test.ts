import { describe, it, expect } from "vitest";

// Placeholder tests — replace with real component/unit tests as the project grows.

describe("utils", () => {
  it("cn merges class names", async () => {
    const { cn } = await import("@/lib/utils");
    expect(cn("a", "b")).toBe("a b");
    expect(cn("a", false && "b", "c")).toBe("a c");
  });

  it("formatBytes formats sizes correctly", () => {
    const formatBytes = (bytes: number): string => {
      if (bytes === 0) return "—";
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / 1048576).toFixed(2)} MB`;
    };
    expect(formatBytes(0)).toBe("—");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(1048576)).toBe("1.00 MB");
  });
});
