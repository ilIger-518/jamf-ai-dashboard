import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, afterAll } from "vitest";
import { startMsw, stopMsw } from "@/__tests__/msw";

afterEach(() => {
  cleanup();
});

beforeAll(() => {
  startMsw();
});

afterAll(() => {
  stopMsw();
});
