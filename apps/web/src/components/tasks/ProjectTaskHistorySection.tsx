import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Pause,
  PlayCircle,
  XCircle,
} from "lucide-react";

import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { ProjectTaskFailureDetails } from "@/components/tasks/ProjectTaskFailureDetails";

type TaskFilter = "all" | "active" | "attention" | "completed";

const TASK_TYPE_LABELS: Record<string, string> = {
  analyze: "AI 分析",
  reanalyze: "AI 重新分析",
  library_scan: "照片扫描",
  photo_quarantine_analysis: "照片隔离分析",
  face_scan: "人脸扫描",
  face_cluster_unknown: "未知人脸聚类",
  face_rematch_unknown: "人脸重匹配",
};

const ACTIVE_STATUSES = new Set(["pending", "queued", "running", "paused"]);
const ATTENTION_STATUSES = new Set(["failed", "completed_with_errors"]);
const COMPLETED_STATUSES = new Set(["success", "succeeded", "completed"]);

export function ProjectTaskHistorySection({ projectId }: { projectId: number | null }) {
  const canLoad = projectId != null;
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null);
  const [filter, setFilter] = useState<TaskFilter>("all");
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.projectTasks(projectId, 8),
    queryFn: () => api.projectTasks.list(projectId!, { limit: 8 }),
    enabled: canLoad,
    refetchInterval: (query) => {
      const hasActive = query.state.data?.items.some((task) =>
        ["pending", "queued", "running"].includes(task.status),
      );
      return hasActive ? 3000 : false;
    },
  });

  const pauseTaskMutation = useMutation({
    mutationFn: (taskId: number) => api.projectTasks.pause(projectId!, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(projectId, 8) });
    },
  });

  const cancelTaskMutation = useMutation({
    mutationFn: (taskId: number) => api.projectTasks.cancel(projectId!, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(projectId, 8) });
    },
  });

  const resumeTaskMutation = useMutation({
    mutationFn: (taskId: number) => api.projectTasks.resume(projectId!, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(projectId, 8) });
    },
  });

  if (!canLoad) return null;

  const items = data?.items ?? [];
  const activeCount = items.filter((task) => ACTIVE_STATUSES.has(task.status)).length;
  const attentionCount = items.filter((task) => ATTENTION_STATUSES.has(task.status)).length;
  const completedCount = items.filter((task) => COMPLETED_STATUSES.has(task.status)).length;
  const otherCount = Math.max(items.length - activeCount - attentionCount - completedCount, 0);
  const statusSegments = [
    { label: "进行中", count: activeCount, className: "bg-primary" },
    { label: "已完成", count: completedCount, className: "bg-green-700" },
    { label: "需关注", count: attentionCount, className: "bg-amber-500" },
    { label: "其他", count: otherCount, className: "bg-stone" },
  ].filter((segment) => segment.count > 0);
  const taskTypeCounts = Array.from(
    items.reduce((counts, task) => {
      counts.set(task.task_type, (counts.get(task.task_type) ?? 0) + 1);
      return counts;
    }, new Map<string, number>()),
  )
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3);
  const maxTypeCount = taskTypeCounts[0]?.[1] ?? 1;
  const filteredItems = items.filter((task) => {
    if (filter === "active") return ACTIVE_STATUSES.has(task.status);
    if (filter === "attention") return ATTENTION_STATUSES.has(task.status);
    if (filter === "completed") return COMPLETED_STATUSES.has(task.status);
    return true;
  });

  return (
    <section className="space-y-4 border-t border-hairline pt-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-heading-md font-semibold text-ink">最近任务</h2>
          <p className="text-caption-sm text-mute">扫描、分析与人脸任务</p>
        </div>
        {data && <span className="text-caption-sm text-mute">共 {data.total} 条</span>}
      </div>

      {isLoading && <p className="text-caption-sm text-mute">正在加载任务历史…</p>}
      {error instanceof Error && (
        <div className="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-caption-sm font-medium text-amber-900">
            {isNotFoundError(error)
              ? "任务历史接口暂不可用"
              : `任务历史加载失败：${error.message}`}
          </p>
          {isNotFoundError(error) && (
            <p className="text-caption-sm text-amber-800">
              当前 API 进程可能还没重启到包含 ProjectTask 历史接口的版本；重启 API 后这里会自动恢复。
            </p>
          )}
        </div>
      )}
      {!isLoading && !error && items.length === 0 && (
        <p className="text-caption-sm text-mute">暂无项目级任务记录。</p>
      )}

      {items.length > 0 && (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-md border border-hairline bg-canvas p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
                  <h3 className="text-body-sm font-semibold text-ink">最近状态</h3>
                </div>
                <span className="text-caption-sm text-mute">最近 {items.length} 条</span>
              </div>
              <div
                className="mt-4 flex h-3 overflow-hidden rounded-full bg-secondary-bg"
                role="img"
                aria-label={`最近任务状态：进行中 ${activeCount}，已完成 ${completedCount}，需关注 ${attentionCount}，其他 ${otherCount}`}
              >
                {statusSegments.map((segment) => (
                  <span
                    key={segment.label}
                    className={segment.className}
                    style={{ width: `${(segment.count / items.length) * 100}%` }}
                  />
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-caption-sm text-mute">
                {statusSegments.map((segment) => (
                  <span key={segment.label} className="inline-flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${segment.className}`} aria-hidden="true" />
                    {segment.label} {segment.count}
                  </span>
                ))}
              </div>
            </div>

            <div className="rounded-md border border-hairline bg-canvas p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-secondary" aria-hidden="true" />
                  <h3 className="text-body-sm font-semibold text-ink">任务类型</h3>
                </div>
                <span className="text-caption-sm text-mute">Top {taskTypeCounts.length}</span>
              </div>
              <div
                className="mt-4 space-y-3"
                role="img"
                aria-label={`任务类型分布：${taskTypeCounts.map(([type, count]) => `${taskTypeLabel(type)} ${count}`).join("，")}`}
              >
                {taskTypeCounts.map(([type, count]) => (
                  <div
                    key={type}
                    className="grid grid-cols-[minmax(88px,1fr)_2fr_auto] items-center gap-2 text-caption-sm"
                  >
                    <span className="truncate text-body" title={taskTypeLabel(type)}>
                      {taskTypeLabel(type)}
                    </span>
                    <span className="h-2 overflow-hidden rounded-full bg-secondary-bg">
                      <span
                        className="block h-full rounded-full bg-secondary"
                        style={{ width: `${(count / maxTypeCount) * 100}%` }}
                      />
                    </span>
                    <strong className="tabular-nums text-ink">{count}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-hairline bg-canvas">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-3 py-2">
              <div className="flex flex-wrap gap-1" role="group" aria-label="筛选最近任务">
                {([
                  ["all", "全部"],
                  ["active", "进行中"],
                  ["attention", "需关注"],
                  ["completed", "已完成"],
                ] as Array<[TaskFilter, string]>).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={filter === value}
                    onClick={() => setFilter(value)}
                    className={[
                      "min-h-11 rounded-sm px-3 text-caption-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer focus-visible:ring-offset-2",
                      filter === value
                        ? "bg-surface-card text-ink"
                        : "text-mute hover:bg-surface-soft hover:text-ink",
                    ].join(" ")}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="text-caption-sm text-mute" aria-live="polite">
                {filteredItems.length} 条
              </span>
            </div>

            <div className="divide-y divide-hairline">
              {filteredItems.map((task) => {
                const latestError = task.latest_failure?.message ?? task.error_message;
                const isExpanded = expandedTaskId === task.id;
                const canPause = ["queued", "running"].includes(task.status);
                const canCancel = ["pending", "queued", "running", "paused"].includes(task.status);
                const canResume = task.status === "paused";
                return (
                  <article key={task.id} className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <span
                          className={[
                            "mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-sm",
                            taskStatusIconClass(task.status),
                          ].join(" ")}
                        >
                          {taskStatusIcon(task.status)}
                        </span>
                        <div className="min-w-0">
                          <p className="break-words text-body-sm font-medium text-ink">
                            #{task.id} · {taskTypeLabel(task.task_type)}
                          </p>
                          <p className="mt-0.5 text-caption-sm tabular-nums text-mute">
                            更新 {formatTaskTime(task.updated_at)}
                            {task.retry_count > 0 ? ` · 重试 ${task.retry_count}` : ""}
                          </p>
                        </div>
                      </div>
                      <span
                        className={[
                          "shrink-0 rounded-full px-2 py-1 text-caption-sm font-medium",
                          taskStatusPillClass(task.status),
                        ].join(" ")}
                      >
                        {taskStatusLabel(task.status)}
                      </span>
                    </div>

                    {latestError && (
                      <div className="mt-2 flex items-start gap-1.5 rounded-sm bg-red-50 px-2.5 py-2">
                        <AlertCircle
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger"
                          aria-hidden="true"
                        />
                        <p className="text-caption-sm text-danger whitespace-pre-wrap break-words">
                          {latestError}
                        </p>
                      </div>
                    )}

                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}
                        className="inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-caption-sm font-medium text-secondary transition-colors hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        详情
                      </button>
                      {canPause && (
                        <button
                          type="button"
                          onClick={() => pauseTaskMutation.mutate(task.id)}
                          disabled={pauseTaskMutation.isPending}
                          className="inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-caption-sm font-medium text-secondary transition-colors hover:bg-surface-soft hover:text-ink disabled:text-stone focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
                        >
                          <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                          {pauseTaskMutation.isPending ? "暂停中…" : "暂停"}
                        </button>
                      )}
                      {canCancel && (
                        <button
                          type="button"
                          onClick={() => cancelTaskMutation.mutate(task.id)}
                          disabled={cancelTaskMutation.isPending}
                          className="inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-caption-sm font-medium text-danger transition-colors hover:bg-red-50 disabled:text-stone focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
                        >
                          <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                          {cancelTaskMutation.isPending ? "取消中…" : "取消"}
                        </button>
                      )}
                      {canResume && (
                        <button
                          type="button"
                          onClick={() => resumeTaskMutation.mutate(task.id)}
                          disabled={resumeTaskMutation.isPending}
                          className="inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-caption-sm font-medium text-primary transition-colors hover:bg-primary/5 hover:text-primary-pressed disabled:text-stone focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
                        >
                          <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />
                          {resumeTaskMutation.isPending ? "恢复中…" : "恢复"}
                        </button>
                      )}
                    </div>

                    {isExpanded && (
                      <div className="mt-2 space-y-3 rounded-md border border-hairline bg-surface-soft p-3">
                        <ProjectTaskFailureDetails
                          projectId={projectId}
                          taskId={task.id}
                          expectedCount={task.failure_count}
                        />
                        <dl className="grid gap-2 sm:grid-cols-3">
                          <TaskFact label="创建时间" value={formatTaskTime(task.created_at)} />
                          <TaskFact label="开始时间" value={formatTaskTime(task.started_at)} />
                          <TaskFact label="完成时间" value={formatTaskTime(task.finished_at)} />
                        </dl>
                        <details className="group rounded-sm border border-hairline bg-canvas px-3 py-2">
                          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-caption-sm font-medium text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer">
                            技术数据
                            <ChevronRight
                              className="h-3.5 w-3.5 transition-transform group-open:rotate-90"
                              aria-hidden="true"
                            />
                          </summary>
                          <div className="space-y-3 border-t border-hairline pt-3">
                            <TaskJsonBlock title="request_params" value={task.request_params} />
                            <TaskJsonBlock title="progress_payload" value={task.progress_payload} />
                            <TaskJsonBlock title="result_payload" value={task.result_payload} />
                          </div>
                        </details>
                      </div>
                    )}
                  </article>
                );
              })}
              {filteredItems.length === 0 && (
                <div className="px-4 py-8 text-center text-body-sm text-mute">
                  当前筛选下暂无任务。
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function TaskFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm bg-canvas px-3 py-2">
      <dt className="text-caption-sm text-mute">{label}</dt>
      <dd className="mt-0.5 break-words text-caption-sm font-medium tabular-nums text-ink">
        {value}
      </dd>
    </div>
  );
}

function taskTypeLabel(taskType: string): string {
  return TASK_TYPE_LABELS[taskType] ?? taskType.split("_").join(" ");
}

function taskStatusLabel(status: string): string {
  if (status === "pending") return "等待中";
  if (status === "queued") return "排队中";
  if (status === "running") return "运行中";
  if (status === "paused") return "已暂停";
  if (status === "failed") return "失败";
  if (status === "completed_with_errors") return "需关注";
  if (status === "cancelled") return "已取消";
  if (COMPLETED_STATUSES.has(status)) return "已完成";
  return status;
}

function taskStatusPillClass(status: string): string {
  if (status === "failed") return "bg-red-50 text-danger";
  if (status === "completed_with_errors" || status === "paused") {
    return "bg-amber-50 text-amber-700";
  }
  if (ACTIVE_STATUSES.has(status)) return "bg-primary/5 text-primary";
  if (COMPLETED_STATUSES.has(status)) return "bg-green-50 text-green-700";
  return "bg-surface-card text-mute";
}

function taskStatusIconClass(status: string): string {
  if (status === "failed") return "bg-red-50 text-danger";
  if (status === "completed_with_errors" || status === "paused") {
    return "bg-amber-50 text-amber-700";
  }
  if (ACTIVE_STATUSES.has(status)) return "bg-primary/5 text-primary";
  if (COMPLETED_STATUSES.has(status)) return "bg-green-50 text-green-700";
  return "bg-surface-card text-mute";
}

function taskStatusIcon(status: string) {
  if (status === "failed" || status === "completed_with_errors") {
    return <AlertTriangle className="h-4 w-4" aria-hidden="true" />;
  }
  if (ACTIVE_STATUSES.has(status)) {
    return <Activity className="h-4 w-4" aria-hidden="true" />;
  }
  if (COMPLETED_STATUSES.has(status)) {
    return <CheckCircle2 className="h-4 w-4" aria-hidden="true" />;
  }
  return <CircleDot className="h-4 w-4" aria-hidden="true" />;
}

function TaskJsonBlock({
  title,
  value,
  tone = "default",
}: {
  title: string;
  value: unknown;
  tone?: "default" | "danger";
}) {
  if (value == null) {
    return (
      <div className="space-y-1">
        <p className="text-caption-sm font-medium text-mute">{title}</p>
        <p className="text-caption-sm text-mute">null</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <p
        className={[
          "text-caption-sm font-medium",
          tone === "danger" ? "text-danger" : "text-mute",
        ].join(" ")}
      >
        {title}
      </p>
      <pre className="max-h-48 overflow-auto rounded-sm border border-hairline bg-canvas px-3 py-2 text-caption-sm text-ink whitespace-pre-wrap break-words">
        {formatTaskJson(value)}
      </pre>
    </div>
  );
}

function formatTaskJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function isNotFoundError(error: Error): boolean {
  return error.message.toLowerCase().includes("not found") || error.message.includes("404");
}

function formatTaskTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
