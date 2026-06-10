export { ApiError } from "./client";
export type {
  AuthSession,
  Photo,
  PhotoDetail,
  PhotoListResponse,
  Project,
  ProjectListResponse,
  SearchResponse,
  SearchResultItem,
} from "./types";

import * as authApi from "./auth";
import { photosApi } from "./photos";
import { projectsApi } from "./projects";
import { searchApi } from "./search";

export const api = {
  auth: authApi,
  photos: photosApi,
  projects: projectsApi,
  search: searchApi,
} as const;
