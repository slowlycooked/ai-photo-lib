export interface QueueTaskStatus {
  queued: number;
  running: number;
  success: number;
  failed: number;
  total: number;
}

export type TaskRunState = "idle" | "queued" | "running" | "succeeded" | "failed" | "mixed";

export interface TaskStatusViewModel {
  state: TaskRunState;
  title: string;
  message: string;
  counts: QueueTaskStatus;
}

function hasWork(status: QueueTaskStatus): boolean {
  return status.total > 0 || status.queued > 0 || status.running > 0;
}

export function buildTaskStatusViewModel(
  status: QueueTaskStatus | null | undefined,
  labels: {
    idleTitle: string;
    runningTitle: string;
    noun: string;
  }
): TaskStatusViewModel {
  const normalized: QueueTaskStatus = {
    queued: status?.queued ?? 0,
    running: status?.running ?? 0,
    success: status?.success ?? 0,
    failed: status?.failed ?? 0,
    total: status?.total ?? 0,
  };

  if (normalized.running > 0) {
    return {
      state: "running",
      title: labels.runningTitle,
      message: `进行中 ${normalized.running} ${labels.noun}`,
      counts: normalized,
    };
  }

  if (normalized.queued > 0) {
    return {
      state: "queued",
      title: labels.idleTitle,
      message: `排队中 ${normalized.queued} ${labels.noun}`,
      counts: normalized,
    };
  }

  if (normalized.failed > 0 && normalized.success > 0) {
    return {
      state: "mixed",
      title: labels.idleTitle,
      message: `完成 ${normalized.success}，失败 ${normalized.failed}`,
      counts: normalized,
    };
  }

  if (normalized.failed > 0) {
    return {
      state: "failed",
      title: labels.idleTitle,
      message: `失败 ${normalized.failed} ${labels.noun}`,
      counts: normalized,
    };
  }

  if (normalized.success > 0 || hasWork(normalized)) {
    return {
      state: "succeeded",
      title: labels.idleTitle,
      message: `已完成 ${normalized.success} ${labels.noun}`,
      counts: normalized,
    };
  }

  return {
    state: "idle",
    title: labels.idleTitle,
    message: `暂无${labels.noun}`,
    counts: normalized,
  };
}

export function stateColorClass(state: TaskRunState): string {
  switch (state) {
    case "running":
      return "text-primary";
    case "failed":
      return "text-amber-600";
    case "mixed":
      return "text-amber-600";
    case "succeeded":
      return "text-green-700";
    default:
      return "text-ink";
  }
}
