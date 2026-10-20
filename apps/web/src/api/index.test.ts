import { describe, expect, it, vi } from "vitest";

import {
  api,
  projectAiJobsApi,
  projectCoreApi,
  projectFacesApi,
  projectPeopleApi,
  projectPhotosApi,
  projectPromptsApi,
  projectScansApi,
  projectSearchApi,
  projectSettingsApi,
  projectTasksApi,
  photoQuarantineApi,
} from "@/api";

describe("api namespace exports", () => {
  it.each([
    ["photos", (signal: AbortSignal) => api.projectPhotos.list(1, 1, 50, null, null, null, "subtree", "cursor", null, signal)],
    ["timeline", (signal: AbortSignal) => api.projectPhotos.timeline(1, null, "subtree", signal)],
    ["search", (signal: AbortSignal) => api.projectSearch.search(1, "test", 1, 50, null, "subtree", "hybrid", false, null, null, null, null, null, null, signal)],
    ["folders", (signal: AbortSignal) => api.folders.tree(1, signal)],
    ["people", (signal: AbortSignal) => api.projectPeople.list(1, true, 200, undefined, signal)],
    ["person detail", (signal: AbortSignal) => api.projectPeople.get(1, 2, 40, signal)],
    ["review", (signal: AbortSignal) => api.projectPeople.reviewPending(1, null, 40, 0, signal)],
    ["quarantine", (signal: AbortSignal) => api.photoQuarantine.list(1, undefined, 24, 0, undefined, undefined, signal)],
    ["tasks", (signal: AbortSignal) => api.projectTasks.list(1, {}, signal)],
    ["jobs", (signal: AbortSignal) => api.projectAiJobs.list(1, undefined, 30, 0, undefined, signal)],
    ["scan status", (signal: AbortSignal) => api.projectScans.status(1, signal)],
    ["face status", (signal: AbortSignal) => api.projectFaces.projectScanStatus(1, signal)],
  ] as const)("propagates cancellation to fetch for %s", async (_name, read) => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    try {
      const result = read(controller.signal);
      expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
      controller.abort();
      await expect(result).rejects.toMatchObject({ name: "AbortError" });
    } finally {
      fetchMock.mockRestore();
    }
  });

  it("exposes project domain APIs without the removed projects facade", () => {
    expect(api.projectCore).toBe(projectCoreApi);
    expect(api.projectAiJobs).toBe(projectAiJobsApi);
    expect(api.projectFaces).toBe(projectFacesApi);
    expect(api.projectPeople).toBe(projectPeopleApi);
    expect(api.projectPhotos).toBe(projectPhotosApi);
    expect(api.projectPrompts).toBe(projectPromptsApi);
    expect(api.projectScans).toBe(projectScansApi);
    expect(api.projectSearch).toBe(projectSearchApi);
    expect(api.projectSettings).toBe(projectSettingsApi);
    expect(api.projectTasks).toBe(projectTasksApi);
    expect(api.photoQuarantine).toBe(photoQuarantineApi);
    expect("projects" in api).toBe(false);
  });
});
