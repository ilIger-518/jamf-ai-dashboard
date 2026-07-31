import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

export const server = setupServer(
  http.get("/api/*", () => HttpResponse.json({ ok: true })),
  http.post("/api/*", () => HttpResponse.json({ ok: true })),
  http.put("/api/*", () => HttpResponse.json({ ok: true })),
  http.patch("/api/*", () => HttpResponse.json({ ok: true })),
  http.delete("/api/*", () => HttpResponse.json({ ok: true }))
);

export const startMsw = () => server.listen({ onUnhandledRequest: "bypass" });
export const stopMsw = () => server.close();
export const resetMsw = () => server.resetHandlers();
