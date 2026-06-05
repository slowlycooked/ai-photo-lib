import { qs, request } from "./client";
import type {
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateListResponse,
  PromptTemplateTestRequest,
  PromptTemplateTestResponse,
  PromptTemplateUpdate,
} from "./types";

export const projectPromptsApi = {
  list: (projectId: number, taskType = "image_analysis") =>
    request<PromptTemplateListResponse>(
      `/projects/${projectId}/prompt-templates${qs({ task_type: taskType })}`,
    ),

  create: (projectId: number, body: PromptTemplateCreate) =>
    request<PromptTemplate>(`/projects/${projectId}/prompt-templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  update: (projectId: number, templateId: number, body: PromptTemplateUpdate) =>
    request<PromptTemplate>(`/projects/${projectId}/prompt-templates/${templateId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: (projectId: number, templateId: number) =>
    request<void>(`/projects/${projectId}/prompt-templates/${templateId}`, {
      method: "DELETE",
    }),

  resetDefault: (projectId: number) =>
    request<PromptTemplate>(`/projects/${projectId}/prompt-templates/reset-default`, {
      method: "POST",
    }),

  test: (projectId: number, body: PromptTemplateTestRequest) =>
    request<PromptTemplateTestResponse>(`/projects/${projectId}/prompt-templates/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
