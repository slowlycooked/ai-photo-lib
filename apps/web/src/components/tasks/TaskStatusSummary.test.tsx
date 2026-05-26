import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TaskStatusSummary } from "@/components/tasks/TaskStatusSummary";

describe("TaskStatusSummary", () => {
  it("shows running title and message for active tasks", () => {
    render(
      <TaskStatusSummary
        status={{ queued: 1, running: 2, success: 3, failed: 0, total: 6 }}
        loading={false}
        idleTitle="AI 图片分析"
        runningTitle="AI 分析进行中…"
        noun="任务"
      />
    );

    expect(screen.getByText("AI 分析进行中…")).toBeInTheDocument();
    expect(screen.getByText("进行中 2 任务")).toBeInTheDocument();
    expect(screen.getByText("排队中")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
  });

  it("shows idle state when status is missing", () => {
    render(
      <TaskStatusSummary
        status={undefined}
        loading={false}
        idleTitle="人脸扫描任务"
        runningTitle="人脸扫描进行中…"
        noun="任务"
      />
    );

    expect(screen.getByText("人脸扫描任务")).toBeInTheDocument();
    expect(screen.getByText("暂无任务")).toBeInTheDocument();
  });
});
