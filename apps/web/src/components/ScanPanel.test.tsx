import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScanPanel } from "./ScanPanel";
import type { ScanStatus } from "@/api";

function buildStatus(overrides: Partial<ScanStatus> = {}): ScanStatus {
  return {
    running: false,
    scanned: 10,
    inserted: 1,
    updated: 2,
    errors: 0,
    current_path: null,
    message: "done",
    recent_errors: [],
    recent_files: [],
    ...overrides,
  };
}

describe("ScanPanel", () => {
  it("shows completed-with-errors when a finished scan has errors", () => {
    render(
      <ScanPanel
        status={buildStatus({
          errors: 1,
          recent_errors: ["bad.jpg: decode failed"],
        })}
        isLoading={false}
        onStart={vi.fn()}
        isPending={false}
      />,
    );

    expect(screen.getByText("扫描完成（含错误）")).toBeInTheDocument();
    expect(screen.getByText("bad.jpg: decode failed")).toBeInTheDocument();
  });
});
