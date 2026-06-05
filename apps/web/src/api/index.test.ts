import { describe, expect, it } from "vitest";

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
} from "@/api";

describe("api namespace exports", () => {
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
    expect("projects" in api).toBe(false);
  });
});
