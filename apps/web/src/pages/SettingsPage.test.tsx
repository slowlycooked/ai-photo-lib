import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type DebugSettingsResponse } from "@/api";
import { DebugLogSettingsCard, SystemHealthCard } from "@/pages/SettingsPage";

const getDebugMock = vi.fn();
const healthMock = vi.fn();
const updateDebugMock = vi.fn();
const configureFrontendLoggerMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      settings: {
        ...actual.api.settings,
        getDebug: (...args: unknown[]) => getDebugMock(...args),
        health: (...args: unknown[]) => healthMock(...args),
        updateDebug: (...args: unknown[]) => updateDebugMock(...args),
      },
    },
  };
});

vi.mock("@/lib/logger", async () => {
  const actual = await vi.importActual<typeof import("@/lib/logger")>("@/lib/logger");
  return {
    ...actual,
    configureFrontendLogger: (...args: unknown[]) => configureFrontendLoggerMock(...args),
  };
});

const response: DebugSettingsResponse = {
  debugMode: "BASIC",
  debugMatrix: {
    frontendLogLevel: "INFO",
    backendLogLevel: "INFO",
    aiLogLevel: "INFO",
    searchLogLevel: "INFO",
    sqlLogLevel: "WARNING",
    taskLogLevel: "INFO",
  },
  presets: {
    OFF: {
      frontendLogLevel: "OFF",
      backendLogLevel: "OFF",
      aiLogLevel: "OFF",
      searchLogLevel: "OFF",
      sqlLogLevel: "OFF",
      taskLogLevel: "OFF",
    },
    BASIC: {
      frontendLogLevel: "INFO",
      backendLogLevel: "INFO",
      aiLogLevel: "INFO",
      searchLogLevel: "INFO",
      sqlLogLevel: "WARNING",
      taskLogLevel: "INFO",
    },
    DEBUG: {
      frontendLogLevel: "DEBUG",
      backendLogLevel: "DEBUG",
      aiLogLevel: "DEBUG",
      searchLogLevel: "DEBUG",
      sqlLogLevel: "DEBUG",
      taskLogLevel: "DEBUG",
    },
    TRACE: {
      frontendLogLevel: "TRACE",
      backendLogLevel: "TRACE",
      aiLogLevel: "TRACE",
      searchLogLevel: "TRACE",
      sqlLogLevel: "TRACE",
      taskLogLevel: "TRACE",
    },
  },
  updatedAt: null,
};

function renderCard() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <DebugLogSettingsCard />
    </QueryClientProvider>
  );
}

function renderHealthCard() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <SystemHealthCard />
    </QueryClientProvider>
  );
}

function getRowSelect(label: string) {
  const row = screen.getByText(label).closest("tr");
  if (!row) {
    throw new Error(`Missing row for ${label}`);
  }
  return within(row).getByRole("combobox");
}

describe("DebugLogSettingsCard", () => {
  beforeEach(() => {
    getDebugMock.mockReset();
    healthMock.mockReset();
    updateDebugMock.mockReset();
    configureFrontendLoggerMock.mockReset();
    getDebugMock.mockResolvedValue(response);
    healthMock.mockResolvedValue({
      status: "warn",
      version: "0.9.0",
      checks: [
        { name: "database", status: "ok", message: "connected" },
        { name: "embedding endpoint configured", status: "warn", message: "not configured" },
      ],
    });
    updateDebugMock.mockResolvedValue(response);
  });

  it("switches all selects to DEBUG when DEBUG mode is chosen", async () => {
    const user = userEvent.setup();
    renderCard();

    await screen.findByText("当前模式：BASIC");
    await user.click(screen.getByRole("button", { name: "DEBUG" }));

    for (const label of ["Frontend", "Backend", "AI", "Search", "SQL", "Task"]) {
      expect(getRowSelect(label)).toHaveValue("DEBUG");
    }
  });

  it("switches mode to CUSTOM when sqlLogLevel is manually changed", async () => {
    const user = userEvent.setup();
    renderCard();

    await screen.findByText("当前模式：BASIC");
    await user.selectOptions(getRowSelect("SQL"), "ERROR");

    expect(screen.getByText("当前模式：CUSTOM")).toBeInTheDocument();
    expect(getRowSelect("SQL")).toHaveValue("ERROR");
  });

  it("switches all selects to OFF when OFF mode is chosen", async () => {
    const user = userEvent.setup();
    renderCard();

    await screen.findByText("当前模式：BASIC");
    await user.click(screen.getByRole("button", { name: "OFF" }));

    for (const label of ["Frontend", "Backend", "AI", "Search", "SQL", "Task"]) {
      expect(getRowSelect(label)).toHaveValue("OFF");
    }
  });

  it("sends the selected mode when saving", async () => {
    const user = userEvent.setup();
    renderCard();

    await screen.findByText("当前模式：BASIC");
    await user.click(screen.getByRole("button", { name: "DEBUG" }));
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    expect(updateDebugMock).toHaveBeenCalledTimes(1);
    expect(updateDebugMock).toHaveBeenCalledWith(
      expect.objectContaining({
        debugMode: "DEBUG",
        debugMatrix: expect.objectContaining({
          frontendLogLevel: "DEBUG",
          backendLogLevel: "DEBUG",
          aiLogLevel: "DEBUG",
          searchLogLevel: "DEBUG",
          sqlLogLevel: "DEBUG",
          taskLogLevel: "DEBUG",
        }),
      }),
    );
  });

  it("shows backend error details when save fails", async () => {
    const user = userEvent.setup();
    updateDebugMock.mockRejectedValue(new ApiError(503, "storage down"));
    renderCard();

    await screen.findByText("当前模式：BASIC");
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    expect(await screen.findByText("保存失败：storage down")).toBeInTheDocument();
  });

  it("keeps a BASIC fallback visible when GET fails", async () => {
    getDebugMock.mockRejectedValue(new Error("network down"));
    renderCard();

    await waitFor(() => {
      expect(screen.getByText(/页面已回退到 BASIC 预设/)).toBeInTheDocument();
    });
    expect(screen.getByText("当前模式：BASIC")).toBeInTheDocument();
  });

  it("shows system health checks", async () => {
    renderHealthCard();

    expect(await screen.findByText("整体状态")).toBeInTheDocument();
    expect(screen.getByText("WARN · v0.9.0")).toBeInTheDocument();
    expect(screen.getByText("database")).toBeInTheDocument();
    expect(screen.getByText("OK · connected")).toBeInTheDocument();
    expect(screen.getByText("embedding endpoint configured")).toBeInTheDocument();
  });
});
