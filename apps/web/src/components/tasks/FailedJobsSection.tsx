import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, RefreshCw } from "lucide-react";

import { api, type AIJob } from "@/api";
import { queryKeys } from "@/api/queryKeys";

function parseErrorMessage(raw: string): { summary: string; detail: string } {
  const trimmed = raw.trim();
  const firstLine = trimmed.split(/\r?\n/, 1)[0] ?? "";

  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      const msg: string | undefined =
        parsed?.error?.message ?? parsed?.message ?? parsed?.detail;
      if (msg) {
        const prefix = raw.slice(0, jsonMatch.index).replace(/:\s*$/, "").trim();
        return {
          summary: prefix ? `${prefix}: ${msg}` : msg,
          detail: trimmed,
        };
      }
    } catch {
      // Keep fallback summary below.
    }
  }

  return {
    summary: firstLine || trimmed,
    detail: trimmed,
  };
}

function FailedJobRow({ job }: { job: AIJob }) {
  const [expanded, setExpanded] = useState(false);
  const errorInfo = job.error_message ? parseErrorMessage(job.error_message) : null;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {
      // Ignore clipboard permission errors in non-secure contexts.
    });
  };

  return (
    <div className="bg-canvas border border-hairline rounded-md px-4 py-2.5 flex items-start gap-3">
      <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-body-sm text-ink truncate">{job.file_name ?? `#${job.photo_id}`}</p>
        <p className="text-caption-sm text-mute">
          prompt v{job.prompt_version ?? "-"} · model {job.model_name ?? "-"}
        </p>
        {errorInfo && (
          <>
            <p className={`text-caption-sm text-mute mt-0.5 ${expanded ? "whitespace-pre-wrap break-all" : "truncate"}`}>
              {expanded ? errorInfo.detail : errorInfo.summary}
            </p>
            {errorInfo.detail && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-caption-sm text-primary hover:text-primary-pressed"
              >
                {expanded ? "收起" : "展开详情"}
              </button>
            )}
            {expanded && (
              <div className="mt-2 space-y-2">
                <div className="bg-surface-soft border border-hairline rounded-md p-2">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-caption-sm text-mute">parse_error</p>
                    {job.parse_error && (
                      <button
                        onClick={() => handleCopy(job.parse_error || "")}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制
                      </button>
                    )}
                  </div>
                  <pre className="text-caption-sm whitespace-pre-wrap break-all">
                    {job.parse_error || "(空)"}
                  </pre>
                </div>

                <div className="bg-surface-soft border border-hairline rounded-md p-2">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-caption-sm text-mute">raw_model_output</p>
                    {job.raw_model_output && (
                      <button
                        onClick={() => handleCopy(job.raw_model_output || "")}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制
                      </button>
                    )}
                  </div>
                  <pre className="text-caption-sm whitespace-pre-wrap break-all max-h-48 overflow-auto">
                    {job.raw_model_output || "(空)"}
                  </pre>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <span className="text-caption-sm text-stone flex-shrink-0">
        {job.retry_count > 0 ? `重试 ${job.retry_count}×` : ""}
      </span>
    </div>
  );
}

export function FailedJobsSection({
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
  const queryClient = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: [listQueryKey, projectId],
    queryFn: () => api.projectAiJobs.list(projectId!, "failed", 50, 0, jobType),
    enabled: projectId != null,
    staleTime: 10_000,
  });

  const retryMutation = useMutation({
    mutationFn: () => api.projectAiJobs.retryFailed(projectId!, jobType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: [listQueryKey, projectId] });
      if (jobType === "face_scan") {
        queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
      }
    },
  });

  const clearFailedJobsMutation = useMutation({
    mutationFn: () => api.projectAiJobs.clearFailed(projectId!, jobType),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: [listQueryKey, projectId] });
    },
    onError: (err: Error) => {
      setError(`清除失败记录失败：${err.message}`);
    },
  });

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  const visible = showAll ? items : items.slice(0, 5);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-amber-500" />
          <h3 className="text-body-sm font-semibold text-ink">{title}</h3>
          <span className="text-caption-sm text-mute">{items.length} 个</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => retryMutation.mutate()}
            disabled={retryMutation.isPending}
            className="flex items-center gap-1 text-btn-sm font-bold text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {retryMutation.isPending ? "重试中…" : "全部重试"}
          </button>
          <button
            onClick={() => clearFailedJobsMutation.mutate()}
            disabled={clearFailedJobsMutation.isPending}
            className="flex items-center gap-1 text-btn-sm font-bold text-danger hover:text-danger-pressed disabled:text-stone transition-colors"
          >
            清除失败记录
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        {visible.map((job) => (
          <FailedJobRow key={job.id} job={job} />
        ))}
      </div>

      {error && <p className="text-caption-sm text-danger">{error}</p>}

      {items.length > 5 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="text-btn-sm text-primary hover:text-primary-pressed"
        >
          {showAll ? "收起" : `显示全部 ${items.length} 个`}
        </button>
      )}
    </section>
  );
}
