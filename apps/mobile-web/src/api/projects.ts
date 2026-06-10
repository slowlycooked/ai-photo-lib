import { request } from "./client";
import type { ProjectListResponse } from "./types";

export const projectsApi = {
  list: () => request<ProjectListResponse>("/projects"),
};
