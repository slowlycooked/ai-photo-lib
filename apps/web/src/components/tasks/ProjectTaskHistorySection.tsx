import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Pause,
  PlayCircle,
  XCircle,
} from "lucide-react";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { ProjectTaskFailureDetails } from "@/components/tasks/ProjectTaskFailureDetails";

export function ProjectTaskHistorySection({ projectId }: { projectId: number | null }) {
  const canLoad = projectId != null;
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.projectTasks(projectId, 8),
    queryFn: () => api.projectTasks.list(projectId!, { limit: 8 }),
    enabled: canLoad,
    refetchInterval: (query) => {
      const hasActive = query.state.data?.items.some((task) =>
        ["queued", "running"].includes(task.status),
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
  return (
    <section className="space-y-3 border-t border-hairline pt-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-body-sm font-semibold text-ink">最近项目任务</h2>
          <p className="text-caption-sm text-mute">统一 ProjectTask 历史，包含扫描、聚类、重匹配等项目级任务。</p>
        </div>
        {data && <span className="text-caption-sm text-mute">共 {data.total} 条</span>}
      </div>

      {isLoading && <p className="text-caption-sm text-mute">正在加载任务历史…</p>}
      {error instanceof Error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 space-y-1">
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
        <div className="divide-y divide-hairline border border-hairline rounded-md bg-canvas overflow-hidden">
          {items.map((task) => {
            const latestError = task.latest_failure?.message ?? task.error_message;
            const isExpanded = expandedTaskId === task.id;
            const canPause = ["queued", "running"].includes(task.status);
            const canCancel = ["queued", "running", "paused"].includes(task.status);
            const canResume = task.status === "paused";
            return (
              <div key={task.id} className="px-4 py-3 space-y-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-body-sm font-medium text-ink">
                    #{task.id} · {task.task_type}
                  </p>
                  <span
                    className={[
                      "text-caption-sm font-medium",
                      task.status === "failed"
                        ? "text-danger"
                        : task.status === "cancelled"
                          ? "text-mute"
                          : ["queued", "running"].includes(task.status)
                            ? "text-primary"
                            : "text-green-700",
                    ].join(" ")}
                  >
                    {task.status}
                  </span>
                </div>
                <p className="text-caption-sm text-mute">
                  created={formatTaskTime(task.created_at)} · updated={formatTaskTime(task.updated_at)}
                </p>
                {latestError && (
                  <p className="text-caption-sm text-danger whitespace-pre-wrap break-all">
                    {latestError}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (isExpanded) {
                        setExpandedTaskId(null);
                        return;
                      }
                      setExpandedTaskId(task.id);
                    }}
                    className="inline-flex items-center gap-1 text-caption-sm font-medium text-secondary hover:text-ink transition-colors"
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                    详情
                  </button>
                  {canPause && (
                    <button
                      type="button"
                      onClick={() => pauseTaskMutation.mutate(task.id)}
                      disabled={pauseTaskMutation.isPending}
                      className="inline-flex items-center gap-1 text-caption-sm font-medium text-secondary hover:text-ink disabled:text-stone transition-colors"
                    >
                      <Pause className="w-3.5 h-3.5" />
                      {pauseTaskMutation.isPending ? "暂停中…" : "暂停"}
                    </button>
                  )}
                  {canCancel && (
                    <button
                      type="button"
                      onClick={() => cancelTaskMutation.mutate(task.id)}
                      disabled={cancelTaskMutation.isPending}
                      className="inline-flex items-center gap-1 text-caption-sm font-medium text-danger hover:text-danger/80 disabled:text-stone transition-colors"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      {cancelTaskMutation.isPending ? "取消中…" : "取消"}
                    </button>
                  )}
                  {canResume && (
                    <button
                      type="button"
                      onClick={() => resumeTaskMutation.mutate(task.id)}
                      disabled={resumeTaskMutation.isPending}
                      className="inline-flex items-center gap-1 text-caption-sm font-medium text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
                    >
                      <PlayCircle className="w-3.5 h-3.5" />
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
                    <TaskJsonBlock title="request_params" value={task.request_params} />
                    <TaskJsonBlock title="progress_payload" value={task.progress_payload} />
                    <TaskJsonBlock title="result_payload" value={task.result_payload} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
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
      <p className={["text-caption-sm font-medium", tone === "danger" ? "text-danger" : "text-mute"].join(" ")}>
        {title}
      </p>
      <pre className="max-h-48 overflow-auto rounded-md bg-canvas border border-hairline px-3 py-2 text-caption-sm text-ink whitespace-pre-wrap break-all">
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
  return date.toLocaleString();
}
