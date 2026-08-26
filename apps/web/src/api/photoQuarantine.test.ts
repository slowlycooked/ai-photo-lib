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

  it("passes the classification filter to the list endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ total: 0, items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await photoQuarantineApi.list(3, "review", 24, 0, undefined, "suspected_duplicate");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/3/photo-quarantine/items?status=review&classification=suspected_duplicate&limit=24&offset=0",
      expect.any(Object),
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

  it("starts analysis with an explicit failed-item retry option", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 88, status: "queued" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await photoQuarantineApi.startRun(3, true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/3/photo-quarantine/runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ retry_failed: true }),
      }),
    );
  });
});
