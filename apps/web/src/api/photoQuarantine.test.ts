import { afterEach, describe, expect, it, vi } from "vitest";

import { photoQuarantineApi } from "@/api/photoQuarantine";

describe("photoQuarantineApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends a bounded batch action contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ requested: 2, succeeded: 2, failed: 0, results: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await photoQuarantineApi.batch(3, "RESTORE", [7, 8]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/3/photo-quarantine/batches",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ action: "RESTORE", item_ids: [7, 8] }),
      }),
    );
  });

  it("starts an idempotent deletion reconciliation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ checked: 3, confirmed: 2, remaining: 1, failed: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await photoQuarantineApi.reconcile(3);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/3/photo-quarantine/reconciliations",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
