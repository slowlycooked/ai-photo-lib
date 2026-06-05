import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsLayout } from "./SettingsLayout";

describe("SettingsLayout", () => {
  it("keeps global and project AI navigation visible on project settings routes", () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/settings/vision-ai"]}>
        <SettingsLayout title="项目设置中心" currentProjectId={7}>
          <div>视觉 AI 表单</div>
        </SettingsLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "常规配置" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "系统监控" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Debug / 日志" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "视觉 AI" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Embedding AI" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Planner AI" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "高级搜索参数" })).toBeInTheDocument();
  });
});
