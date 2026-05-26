import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

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
    queryFn: () => api.projects.aiJobs(projectId!, undefined, 30, 0, jobType),
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

  const items = (data?.items ?? []).slice(0, 15);
  if (items.length === 0) return null;

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <Loader2 className="w-4 h-4 text-primary" />
        <h3 className="text-body-sm font-semibold text-ink">{title}</h3>
        <span className="text-caption-sm text-mute">最近 {items.length} 条</span>
      </div>
      <div className="space-y-1.5 max-h-72 overflow-auto pr-1">
        {items.map((job) => {
          const status = asJobStatus(job.status);
          const fileName = job.file_name ?? `photo#${job.photo_id}`;
          return (
            <div
              key={job.id}
              className="bg-canvas border border-hairline rounded-md px-4 py-2.5 space-y-0.5"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-body-sm text-ink truncate" title={fileName}>
                  {fileName}
                </p>
                <span className={`text-caption-sm font-medium whitespace-nowrap ${STATUS_CLASS[status]}`}>
                  {STATUS_LABEL[status]}
                </span>
              </div>
              <p className="text-caption-sm text-mute">job#{job.id} · retry={job.retry_count}</p>
              {status === "failed" && job.error_message && (
                <div className="flex items-start gap-2 pt-0.5">
                  <AlertCircle className="w-3.5 h-3.5 text-danger shrink-0 mt-0.5" />
                  <p className="text-caption-sm text-danger whitespace-pre-wrap break-all">
                    {job.error_message}
                  </p>
                </div>
              )}
              {status === "success" && (
                <div className="flex items-center gap-1.5 pt-0.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-700" />
                  <p className="text-caption-sm text-green-700">处理完成</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}