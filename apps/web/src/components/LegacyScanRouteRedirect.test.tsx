import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LegacyScanRouteRedirect } from "./LegacyScanRouteRedirect";
import { logger } from "@/lib/logger";

vi.mock("@/lib/logger", async () => {
  const actual = await vi.importActual<typeof import("@/lib/logger")>("@/lib/logger");
  return {
    ...actual,
    logger: {
      ...actual.logger,
      warn: vi.fn(),
    },
  };
});

describe("LegacyScanRouteRedirect", () => {
  it("redirects /scan to canonical tasks tab and emits deprecation warning", () => {
    render(
      <MemoryRouter initialEntries={["/scan"]}>
        <Routes>
          <Route path="/scan" element={<LegacyScanRouteRedirect />} />
          <Route path="/tasks" element={<div>Tasks Page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Tasks Page")).toBeInTheDocument();
    expect(logger.warn).toHaveBeenCalledWith(
      "deprecated frontend route used",
      expect.objectContaining({
        legacyPath: "/scan",
        successorPath: "/tasks?tab=scan",
      }),
    );
  });
});
