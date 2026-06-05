import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type PromptTemplate } from "@/api";
import { PromptSettingsSection } from "@/components/project-ai-settings/PromptSettingsSection";

const promptTemplatesMock = vi.fn();
const photosMock = vi.fn();
const aiJobsMock = vi.fn();
const createPromptTemplateMock = vi.fn();
const testPromptTemplateMock = vi.fn();
const updateAiSettingsMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projectAiJobs: {
        ...actual.api.projectAiJobs,
        list: (...args: unknown[]) => aiJobsMock(...args),
      },
      projectPhotos: {
        ...actual.api.projectPhotos,
        list: (...args: unknown[]) => photosMock(...args),
      },
      projectPrompts: {
        ...actual.api.projectPrompts,
        list: (...args: unknown[]) => promptTemplatesMock(...args),
        create: (...args: unknown[]) => createPromptTemplateMock(...args),
        test: (...args: unknown[]) => testPromptTemplateMock(...args),
      },
      projectSettings: {
        ...actual.api.projectSettings,
        updateAi: (...args: unknown[]) => updateAiSettingsMock(...args),
      },
    },
  };
});

function makeTemplate(overrides: Partial<PromptTemplate>): PromptTemplate {
  return {
    id: overrides.id ?? 1,
    project_id: overrides.project_id ?? 1,
    name: overrides.name ?? "默认模板",
    task_type: "image_analysis",
    system_prompt: null,
    user_prompt: overrides.user_prompt ?? "请重点分析以下内容：\n- 场景",
    output_schema: null,
    is_active: overrides.is_active ?? false,
    version: overrides.version ?? 1,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
  };
}

function renderSection(projectId: number, onMessage: (message: string) => void = () => undefined) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <PromptSettingsSection
        projectId={projectId}
        modelForm={{
          provider: "llama-server",
          endpoint_url: "http://model.local",
          model_name: "qwen",
          temperature: 0,
          top_p: 0.8,
          max_tokens: 1024,
          retry_count: 1,
          output_language: "中文",
          json_parse_strategy: "auto_extract",
        }}
        onMessage={onMessage}
      />
    </QueryClientProvider>
  );
}

describe("PromptSettingsSection", () => {
  beforeEach(() => {
    promptTemplatesMock.mockReset();
    photosMock.mockReset();
    aiJobsMock.mockReset();
    createPromptTemplateMock.mockReset();
    testPromptTemplateMock.mockReset();
    updateAiSettingsMock.mockReset();

    photosMock.mockResolvedValue({ items: [], total: 0 });
    aiJobsMock.mockResolvedValue({ items: [], total: 0 });
    testPromptTemplateMock.mockResolvedValue({
      success: true,
      raw_output: "{}",
      parsed_json: {},
      error: null,
      duration_ms: 10,
    });
  });

  it("loads the active prompt template for the current project", async () => {
    promptTemplatesMock.mockResolvedValue({
      total: 2,
      items: [
        makeTemplate({ id: 11, project_id: 1, name: "模板 A", version: 1, is_active: false }),
        makeTemplate({ id: 12, project_id: 1, name: "模板 B", version: 2, is_active: true }),
      ],
    });

    renderSection(1);

    expect(screen.getByText("Prompt 测试 · 稳定")).toBeInTheDocument();
    expect(screen.getByText(/Prompt 测试支持项目模板、测试图片、解析结果与本地历史回看/)).toBeInTheDocument();
    expect(await screen.findByDisplayValue("模板 B")).toBeInTheDocument();
    expect(promptTemplatesMock).toHaveBeenCalledWith(1);
  });

  it("resets prompt selection when project changes", async () => {
    const user = userEvent.setup();

    promptTemplatesMock.mockImplementation((projectId: number) => {
      if (projectId === 1) {
        return Promise.resolve({
          total: 2,
          items: [
            makeTemplate({ id: 21, project_id: 1, name: "项目1模板A", version: 1, is_active: true }),
            makeTemplate({ id: 22, project_id: 1, name: "项目1模板B", version: 2, is_active: false }),
          ],
        });
      }
      return Promise.resolve({
        total: 1,
        items: [
          makeTemplate({ id: 31, project_id: 2, name: "项目2模板", version: 1, is_active: true }),
        ],
      });
    });

    const { rerender } = renderSection(1);

    expect(await screen.findByDisplayValue("项目1模板A")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "v2 · 项目1模板B" }));
    expect(await screen.findByDisplayValue("项目1模板B")).toBeInTheDocument();

    const nextClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    rerender(
      <QueryClientProvider client={nextClient}>
        <PromptSettingsSection
          projectId={2}
          modelForm={{
            provider: "llama-server",
            endpoint_url: "http://model.local",
            model_name: "qwen",
            temperature: 0,
            top_p: 0.8,
            max_tokens: 1024,
            retry_count: 1,
            output_language: "中文",
            json_parse_strategy: "auto_extract",
          }}
          onMessage={() => undefined}
        />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue("项目2模板")).toBeInTheDocument();
    });
    expect(screen.queryByDisplayValue("项目1模板B")).not.toBeInTheDocument();
    expect(promptTemplatesMock).toHaveBeenCalledWith(2);
  });

  it("creates a new prompt template and reports success message", async () => {
    const user = userEvent.setup();
    const onMessage = vi.fn();

    promptTemplatesMock.mockResolvedValue({ total: 0, items: [] });
    createPromptTemplateMock.mockResolvedValue(
      makeTemplate({ id: 41, project_id: 1, name: "图片分析模板", version: 1, is_active: true })
    );

    renderSection(1, onMessage);

    await user.click(await screen.findByRole("button", { name: "保存为新版本" }));

    await waitFor(() => {
      expect(createPromptTemplateMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          name: "图片分析模板",
          task_type: "image_analysis",
          is_active: true,
        })
      );
    });
    expect(onMessage).toHaveBeenCalledWith("Prompt 已保存为新版本 v1");
  });

  it("reports prompt test failure message when backend returns error", async () => {
    const user = userEvent.setup();
    const onMessage = vi.fn();

    promptTemplatesMock.mockResolvedValue({
      total: 1,
      items: [makeTemplate({ id: 51, project_id: 1, name: "测试模板", version: 3, is_active: true })],
    });
    photosMock.mockResolvedValue({
      total: 1,
      items: [{ id: 901, file_name: "a.jpg" }],
    });
    testPromptTemplateMock.mockRejectedValue(new Error("network down"));

    renderSection(1, onMessage);

    await screen.findByDisplayValue("测试模板");
    await user.selectOptions(screen.getByRole("combobox"), "901");
    await user.click(screen.getByRole("button", { name: "测试当前 Prompt" }));

    await waitFor(() => {
      expect(testPromptTemplateMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ image_id: 901 })
      );
    });
    expect(onMessage).toHaveBeenCalledWith("Prompt 测试失败：network down");
  });

  it("saves prompt then runs prompt test successfully", async () => {
    const user = userEvent.setup();
    const onMessage = vi.fn();

    promptTemplatesMock.mockResolvedValue({ total: 0, items: [] });
    createPromptTemplateMock.mockResolvedValue(
      makeTemplate({ id: 61, project_id: 1, name: "链路模板", version: 1, is_active: true })
    );
    photosMock.mockResolvedValue({
      total: 1,
      items: [{ id: 902, file_name: "chain.jpg" }],
    });
    testPromptTemplateMock.mockResolvedValue({
      success: true,
      raw_output: "ok",
      parsed_json: { scene_tags: ["室内"] },
      error: null,
      duration_ms: 22,
    });

    renderSection(1, onMessage);

    await user.click(await screen.findByRole("button", { name: "保存为新版本" }));
    await waitFor(() => {
      expect(createPromptTemplateMock).toHaveBeenCalledTimes(1);
    });

    await user.selectOptions(screen.getByRole("combobox"), "902");
    await user.click(screen.getByRole("button", { name: "测试当前 Prompt" }));

    await waitFor(() => {
      expect(testPromptTemplateMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ image_id: 902 })
      );
    });
    expect(onMessage).toHaveBeenCalledWith("Prompt 已保存为新版本 v1");
    expect(onMessage).toHaveBeenCalledWith("Prompt 测试成功");
    expect(screen.getAllByText("解析成功").length).toBeGreaterThan(0);
  });

  it("clears previous prompt test result when switching project", async () => {
    const user = userEvent.setup();

    promptTemplatesMock.mockImplementation((projectId: number) => {
      if (projectId === 1) {
        return Promise.resolve({
          total: 1,
          items: [
            makeTemplate({ id: 71, project_id: 1, name: "项目1模板", version: 1, is_active: true }),
          ],
        });
      }
      return Promise.resolve({
        total: 1,
        items: [
          makeTemplate({ id: 72, project_id: 2, name: "项目2模板", version: 1, is_active: true }),
        ],
      });
    });
    photosMock.mockImplementation((projectId: number) => {
      if (projectId === 1) {
        return Promise.resolve({ total: 1, items: [{ id: 903, file_name: "p1.jpg" }] });
      }
      return Promise.resolve({ total: 0, items: [] });
    });
    testPromptTemplateMock.mockResolvedValue({
      success: true,
      raw_output: "project1 output",
      parsed_json: { scene_tags: ["户外"] },
      error: null,
      duration_ms: 11,
    });

    const { rerender } = renderSection(1);

    await screen.findByDisplayValue("项目1模板");
    await user.selectOptions(screen.getByRole("combobox"), "903");
    await user.click(screen.getByRole("button", { name: "测试当前 Prompt" }));

    await screen.findByText("project1 output");

    const nextClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    rerender(
      <QueryClientProvider client={nextClient}>
        <PromptSettingsSection
          projectId={2}
          modelForm={{
            provider: "llama-server",
            endpoint_url: "http://model.local",
            model_name: "qwen",
            temperature: 0,
            top_p: 0.8,
            max_tokens: 1024,
            retry_count: 1,
            output_language: "中文",
            json_parse_strategy: "auto_extract",
          }}
          onMessage={() => undefined}
        />
      </QueryClientProvider>
    );

    await screen.findByDisplayValue("项目2模板");
    expect(screen.queryByText("project1 output")).not.toBeInTheDocument();
    expect(screen.getByText("(暂无测试结果)")).toBeInTheDocument();
  });
});
