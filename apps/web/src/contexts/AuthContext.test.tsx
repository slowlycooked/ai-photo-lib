import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";

const loginMock = vi.fn();
const logoutMock = vi.fn();
const meMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    authApi: {
      login: (...args: unknown[]) => loginMock(...args),
      logout: (...args: unknown[]) => logoutMock(...args),
      me: (...args: unknown[]) => meMock(...args),
    },
  };
});

const viewerSession = {
  user_id: 2,
  username: "viewer",
  display_name: "Viewer",
  role: "viewer" as const,
  capabilities: [],
  sessionTimeoutMinutes: 60,
};

describe("AuthProvider", () => {
  beforeEach(() => {
    loginMock.mockReset();
    logoutMock.mockReset();
    meMock.mockReset();
    meMock.mockRejectedValue(new Error("anonymous"));
  });

  it("clears cached data before exposing a newly authenticated user", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    );
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe("anonymous"));
    queryClient.setQueryData(["photos", 1], { items: [{ id: 99 }] });
    loginMock.mockResolvedValue(viewerSession);

    await act(async () => {
      await result.current.login("viewer", "secret");
    });

    expect(queryClient.getQueryData(["photos", 1])).toBeUndefined();
    expect(result.current.session).toEqual(viewerSession);
    expect(result.current.status).toBe("authenticated");
  });
});
