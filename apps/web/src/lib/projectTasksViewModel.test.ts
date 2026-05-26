import { describe, expect, it } from "vitest";

import { buildTaskStatusViewModel, stateColorClass } from "@/lib/projectTasksViewModel";

describe("projectTasksViewModel", () => {
  it("prefers running state when running tasks exist", () => {
    const vm = buildTaskStatusViewModel(
      { queued: 2, running: 1, success: 5, failed: 0, total: 8 },
      { idleTitle: "AI 图片分析", runningTitle: "AI 分析进行中…", noun: "任务" }
    );

    expect(vm.state).toBe("running");
    expect(vm.title).toBe("AI 分析进行中…");
    expect(vm.message).toContain("进行中 1");
  });

  it("falls back to failed state when only failures exist", () => {
    const vm = buildTaskStatusViewModel(
      { queued: 0, running: 0, success: 0, failed: 3, total: 3 },
      { idleTitle: "人脸扫描任务", runningTitle: "人脸扫描进行中…", noun: "任务" }
    );

    expect(vm.state).toBe("failed");
    expect(vm.message).toBe("失败 3 任务");
    expect(stateColorClass(vm.state)).toBe("text-amber-600");
  });

  it("returns idle state when no task counters exist", () => {
    const vm = buildTaskStatusViewModel(undefined, {
      idleTitle: "AI 图片分析",
      runningTitle: "AI 分析进行中…",
      noun: "任务",
    });

    expect(vm.state).toBe("idle");
    expect(vm.counts.total).toBe(0);
    expect(vm.message).toBe("暂无任务");
    expect(stateColorClass(vm.state)).toBe("text-ink");
  });
});
