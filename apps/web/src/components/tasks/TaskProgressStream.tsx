import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { api } from "@/api";

type JobStatus = "queued" | "running" | "success" | "failed";

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "排队中",
  running: "进行中",
  success: "成功",
  failed: "失败",
};

const STATUS_CLASS: Record<JobStatus, string> = {
  queued: "text-mute",
  running: "text-primary",
  success: "text-green-700",
  failed: "text-danger",
};

const STATUS_DOT_CLASS: Record<JobStatus, string> = {
  queued: "bg-stone",
  running: "bg-primary",
  success: "bg-green-700",
  failed: "bg-danger",
};

function asJobStatus(value: string): JobStatus {
  if (value === "queued" || value === "running" || value === "success" || value === "failed") {
    return value;
  }
  return "queued";
}

export function TaskProgressStream({
  projectId,
  title,
  jobType,
  listQueryKey,
}: {
  projectId: number | null;
  title: string;
  jobType: string;
  listQueryKey: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: [listQueryKey, projectId],
    queryFn: () => api.projectAiJobs.list(projectId!, undefined, 30, 0, jobType),
    enabled: projectId != null,
    staleTime: 0,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const hasActive = items.some((item) => item.status === "queued" || item.status === "running");
      return hasActive ? 1500 : 8000;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-mute text-body-sm px-1 py-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>加载任务进度中…</span>
      </div>
    );
  }

  const items = (data?.items ?? []).slice(0, 6);
  if (items.length === 0) return null;
  const hasActive = items.some((item) => item.status === "queued" || item.status === "running");

  return (
    <section className="rounded-md border border-hairline bg-canvas p-4" aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-body-sm font-semibold text-ink">实时活动</h3>
        </div>
        {hasActive ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/5 px-2 py-1 text-caption-sm font-medium text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
            LIVE
          </span>
        ) : (
          <span className="text-caption-sm text-mute">最近 {items.length} 条</span>
        )}
      </div>

      <ol className="mt-4 space-y-0">
        {items.map((job, index) => {
          const status = asJobStatus(job.status);
          const fileName = job.file_name ?? `photo#${job.photo_id}`;
          return (
            <li
              key={job.id}
              className="relative grid grid-cols-[12px_minmax(0,1fr)] gap-3 pb-4 last:pb-0"
            >
              <div className="relative flex justify-center">
                <span
                  className={`relative z-10 mt-1 h-2.5 w-2.5 rounded-full ${STATUS_DOT_CLASS[status]}`}
                  aria-hidden="true"
                />
                {index < items.length - 1 && (
                  <span className="absolute bottom-0 top-3 w-px bg-hairline" aria-hidden="true" />
                )}
              </div>

              <div className="min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 break-words text-body-sm font-medium text-ink">{fileName}</p>
                  <span className={`shrink-0 text-caption-sm font-medium ${STATUS_CLASS[status]}`}>
                    {STATUS_LABEL[status]}
                  </span>
                </div>
                <p className="text-caption-sm tabular-nums text-mute">
                  #{job.id}{job.retry_count > 0 ? ` · 重试 ${job.retry_count}` : ""}
                </p>
                {status === "failed" && job.error_message && (
                  <div className="mt-1 flex items-start gap-1.5 rounded-sm bg-red-50 px-2 py-1.5">
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" aria-hidden="true" />
                    <p className="text-caption-sm text-danger whitespace-pre-wrap break-words">
                      {job.error_message}
                    </p>
                  </div>
                )}
                {status === "success" && (
                  <div className="mt-1 flex items-center gap-1.5 text-caption-sm text-green-700">
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>处理完成</span>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
