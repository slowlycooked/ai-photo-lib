import { request } from "./client";

export type SystemRole = "admin" | "project_manager" | "viewer";
export type ProjectRole = "manager" | "viewer";
export type AICapability = "vision" | "embedding" | "query_planner";

export interface UserResponse {
  id: number;
  username: string;
  display_name: string | null;
  role: SystemRole;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  total: number;
  items: UserResponse[];
}

export interface UserCreate {
  username: string;
  password: string;
  display_name?: string | null;
  role: SystemRole;
  status?: string;
}

export interface UserUpdate {
  display_name?: string | null;
  role?: SystemRole;
  status?: string;
}

export interface ProjectMembershipResponse {
  id: number;
  project_id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  project_role: ProjectRole;
  created_at: string;
  updated_at: string;
}

export interface ProjectMembershipListResponse {
  total: number;
  items: ProjectMembershipResponse[];
}

export interface UserProjectAccessResponse {
  project_id: number;
  project_name: string;
  project_description: string | null;
  project_role: ProjectRole;
  created_at: string;
  updated_at: string;
}

export interface UserProjectAccessListResponse {
  total: number;
  items: UserProjectAccessResponse[];
}

export interface UserProjectAccessUpdate {
  project_role: ProjectRole;
}

export interface AIServiceProfile {
  id: number;
  name: string;
  capability: AICapability;
  provider: string;
  endpoint_url: string | null;
  has_api_key: boolean;
  model_name: string;
  model_params_json: Record<string, unknown> | null;
  timeout_seconds: number;
  enabled: boolean;
  visible_to_projects: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIServiceProfileListResponse {
  total: number;
  items: AIServiceProfile[];
}

export interface AIServiceProfileCreate {
  name: string;
  capability: AICapability;
  provider: string;
  endpoint_url: string;
  api_key?: string | null;
  model_name: string;
  timeout_seconds?: number;
  enabled?: boolean;
  visible_to_projects?: boolean;
  is_default?: boolean;
}

export type AIServiceProfileUpdate = Partial<AIServiceProfileCreate>;

export const adminApi = {
  listUsers: () => request<UserListResponse>("/users"),
  createUser: (body: UserCreate) =>
    request<UserResponse>("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateUser: (userId: number, body: UserUpdate) =>
    request<UserResponse>(`/users/${userId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteUser: (userId: number) => request<void>(`/users/${userId}`, { method: "DELETE" }),
  resetPassword: (userId: number, password: string) =>
    request<UserResponse>(`/users/${userId}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    }),
  listUserProjectAccess: (userId: number) =>
    request<UserProjectAccessListResponse>(`/users/${userId}/projects`),
  upsertUserProjectAccess: (userId: number, projectId: number, body: UserProjectAccessUpdate) =>
    request<UserProjectAccessListResponse>(`/users/${userId}/projects/${projectId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteUserProjectAccess: (userId: number, projectId: number) =>
    request<UserProjectAccessListResponse>(`/users/${userId}/projects/${projectId}`, {
      method: "DELETE",
    }),

  listProjectMembers: (projectId: number) =>
    request<ProjectMembershipListResponse>(`/projects/${projectId}/members`),
  upsertProjectMember: (projectId: number, userId: number, projectRole: ProjectRole) =>
    request<ProjectMembershipListResponse>(`/projects/${projectId}/members`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, project_role: projectRole }),
    }),
  deleteProjectMember: (projectId: number, userId: number) =>
    request<void>(`/projects/${projectId}/members/${userId}`, { method: "DELETE" }),

  listAIProfiles: () => request<AIServiceProfileListResponse>("/settings/ai-profiles"),
  createAIProfile: (body: AIServiceProfileCreate) =>
    request<AIServiceProfileListResponse>("/settings/ai-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  importAIProfilesFromEnv: () =>
    request<AIServiceProfileListResponse>("/settings/ai-profiles/import-env", {
      method: "POST",
    }),
  updateAIProfile: (profileId: number, body: AIServiceProfileUpdate) =>
    request<AIServiceProfileListResponse>(`/settings/ai-profiles/${profileId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
