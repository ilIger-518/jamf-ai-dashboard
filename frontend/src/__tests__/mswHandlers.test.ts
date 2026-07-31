import { beforeEach, describe, expect, it } from "vitest";
import { server, startMsw, stopMsw, resetMsw } from "@/__tests__/msw";
import { http, HttpResponse } from "msw";

describe("MSW handlers", () => {
  beforeEach(() => {
    stopMsw();
    resetMsw();
    startMsw();
  });

  it("handles a typical API route", async () => {
    const response = await fetch("/api/v1/health");
    expect(response.ok).toBe(true);
  });

  it("allows custom override handlers", async () => {
    server.use(
      http.get("/api/v1/servers", () => HttpResponse.json([{ id: "1", name: "Server 1" }])),
    );

    const response = await fetch("/api/v1/servers");
    const body = await response.json();

    expect(body).toEqual([{ id: "1", name: "Server 1" }]);
  });
});
