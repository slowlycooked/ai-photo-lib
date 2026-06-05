import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Loader2, RefreshCw, Play } from "lucide-react";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";

export function AIPanel({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);

  const wasActiveRef = useRef(false);

  const { data: status, isLoading } = useQuery({
    queryKey: queryKeys.aiStatus(projectId),
    queryFn: () => api.projectAiJobs.status(projectId),
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && (d.queued > 0 || d.running > 0) ? 3000 : 15000;
    },
  });

  // When the queue drains (active → idle), refresh the photo grid so status
  // badges ("待分析" → "AI 已分析") update without a manual page reload.
  useEffect(() => {
    const isActive = !!status && (status.queued > 0 || status.running > 0);
    if (wasActiveRef.current && !isActive && status) {
      queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoAiBase(projectId) });
    }
    wasActiveRef.current = isActive;
  }, [status, queryClient, projectId]);

  const startMutation = useMutation({
    mutationFn: () => api.projectAiJobs.startAnalysis(projectId),
    onSuccess: (data) => {
      if (data.created_jobs > 0) {
        setMessage(`已创建 ${data.created_jobs} 个分析任务`);
      } else {
        setMessage("所有照片已在分析队列中，无需重复创建");
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`启动失败：${err.message}`),
  });

  const retryMutation = useMutation({
    mutationFn: () => api.projectAiJobs.retryFailed(projectId),
    onSuccess: (data) => {
      setMessage(`已重新排队 ${data.retried_jobs} 个失败任务`);
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      setTimeout(() => setMessage(null), 4000);
    },
    onError: (err: Error) => setMessage(`重试失败：${err.message}`),
  });

  const isRunning = status && status.running > 0;

  return (
    <div className="bg-canvas border border-hairline rounded-md p-4 space-y-3">
      {/* Title row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-mute" />
          ) : isRunning ? (
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
          ) : (
            <Brain className="w-4 h-4 text-primary" />
          )}
          <span className="text-body-sm font-semibold text-ink">
            {isRunning ? "AI 分析进行中…" : "AI 图片分析"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {status && status.failed > 0 && (
            <button
              type="button"
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
              className="flex items-center gap-1 text-btn-sm font-bold text-amber-600 hover:text-amber-700 disabled:text-stone transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {retryMutation.isPending ? "重试中…" : "重试失败"}
            </button>
          )}
          <button
            type="button"
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="flex items-center gap-1 text-btn-sm font-bold text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            {startMutation.isPending ? "启动中…" : "开始分析"}
          </button>
        </div>
      </div>

      {/* Feedback message */}
      {message && (
        <p className="text-caption-sm text-mute">{message}</p>
      )}
    </div>
  );
}
