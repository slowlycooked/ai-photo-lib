import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProjectSearchSettingsPanel from "./ProjectSearchSettingsPanel";

const getSearchSettingsMock = vi.fn();
const getEffectiveSettingsMock = vi.fn();
const updateSearchSettingsMock = vi.fn();
const resetSearchSettingsMock = vi.fn();

vi.mock("@/api", () => ({
  api: {
    projects: {
      getSearchSettings: (...args: unknown[]) => getSearchSettingsMock(...args),
      getEffectiveSettings: (...args: unknown[]) => getEffectiveSettingsMock(...args),
      updateSearchSettings: (...args: unknown[]) => updateSearchSettingsMock(...args),
      resetSearchSettings: (...args: unknown[]) => resetSearchSettingsMock(...args),
    },
  },
}));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <ProjectSearchSettingsPanel projectId={7} />
    </QueryClientProvider>,
  );
}

describe("ProjectSearchSettingsPanel", () => {
  it("renders effective setting source metadata", async () => {
    getSearchSettingsMock.mockResolvedValue({
      id: 1,
      project_id: 7,
      default_mode: "hybrid",
      keyword_top_k: 2000,
      vector_top_k: 321,
      page_size_default: 50,
      page_size_max: 200,
      rrf_k: 60,
      keyword_weight: 0.55,
      vector_weight: 0.45,
      vector_min_score: 0.25,
      keyword_field_weights: null,
      vector_field_weights: null,
      ocr_query_vector_field_weights: null,
      enable_query_understanding: true,
      enable_structured_filters: false,
      enable_semantic_tag_boost: false,
      search_quality_settings: {
        vector_strict_score: 0.5,
      },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    getEffectiveSettingsMock.mockResolvedValue({
      search: {
        vector_top_k: { value: 321, source: "project_search_settings" },
        vector_field_weights: {
          value: {
            content_embedding: 0.5,
            tag_embedding: 0.25,
            caption_embedding: 0.2,
            ocr_embedding: 0.05,
          },
          source: "project_embedding_settings",
        },
        ocr_vector_field_weights: {
          value: {
            content_embedding: 0.35,
            tag_embedding: 0.15,
            caption_embedding: 0.1,
            ocr_embedding: 0.4,
          },
          source: "global_config",
        },
        vector_strict_score: {
          value: 0.5,
          source: "project_search_settings.search_quality_settings",
        },
        query_planner_enabled: {
          value: true,
          source: "project_query_planner_settings",
        },
        query_planner_model_name: {
          value: "qwen3-4b-query-planner",
          source: "project_query_planner_settings",
        },
      },
    });

    renderPanel();

    const heading = await screen.findByText("H. Effective Settings 来源");
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    const scoped = within(section as HTMLElement);

    expect(scoped.getByText("向量召回量")).toBeInTheDocument();
    expect(scoped.getByText("搜索设置表")).toBeInTheDocument();
    expect(scoped.getByText("Embedding 设置表")).toBeInTheDocument();
    expect(scoped.getByText("搜索质量 JSON")).toBeInTheDocument();
    expect(scoped.getAllByText("Query Planner 设置表")).toHaveLength(2);
    expect(scoped.getByText("qwen3-4b-query-planner")).toBeInTheDocument();
  });
});
