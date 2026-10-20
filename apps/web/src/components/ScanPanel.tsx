import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, AlertCircle, FolderSearch, XCircle } from "lucide-react";
import type { ScanStatus } from "@/api";
import { ProjectTaskFailureDetails } from "@/components/tasks/ProjectTaskFailureDetails";

// Messages that are normal lifecycle states, not errors.
const LABEL: Record<string, string> = {
  idle: "待扫描",
  scanning: "正在扫描照片目录…",
  rebuilding: "正在清理旧照片库索引…",
  "reindexing (all)": "正在重新提取元数据（全部）…",
  "reindexing (missing_metadata)": "正在重新提取元数据（缺失）…",
  "reindexing (missing_location)": "正在补全地点信息（仅缺失地点）…",
  done: "扫描完成",
  done_with_errors: "扫描完成（含错误）",
  cancelling: "正在取消…",
  cancelled: "已取消",
};

const STAGE_LABEL: Record<string, string> = {
  rebuild: "清理旧索引",
  discovery: "发现文件",
  prepare: "预处理",
  persist: "落库",
  cleanup: "清理与重算",
  done: "完成",
};

interface ScanPanelProps {
  projectId: number | null;
  status: ScanStatus | undefined;
  isLoading: boolean;
  onStart: (rebuild: boolean) => void;
  isPending: boolean;
  /** Network / API-level error from the start-scan mutation. */
  mutationError?: string | null;
  /** Trigger re-extraction of EXIF metadata for photos already in the DB. */
  onReindex?: (scope: "all" | "missing_metadata" | "missing_location") => void;
  isReindexPending?: boolean;
  onCancel?: () => void;
  isCancelPending?: boolean;
}

export function ScanPanel({
  projectId,
  status,
  isLoading,
  onStart,
  isPending,
  mutationError,
  onReindex,
  isReindexPending,
  onCancel,
  isCancelPending,
}: ScanPanelProps) {
  const [rebuild, setRebuild] = useState(false);

  useEffect(() => {
    setRebuild(false);
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-mute text-body-sm px-1 py-3">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>加载中…</span>
      </div>
    );
  }

  if (!status) return null;

  // A status message that is not a known lifecycle state is a scan error.
  const statusError =
    !status.running && status.message && !(status.message in LABEL)
      ? status.message
      : null;

  const recentFiles = status.recent_files ?? [];
  const hasScanErrors = status.errors > 0;
  const stageLabel = status.current_stage ? STAGE_LABEL[status.current_stage] ?? status.current_stage : null;
  const displayLabel = status.running
    ? status.message === "cancelling"
      ? LABEL.cancelling
      : LABEL[status.message] ?? LABEL.scanning
    : hasScanErrors && status.message === "done"
      ? LABEL.done_with_errors
      : LABEL[status.message] ?? status.message;

  const showError = mutationError ?? statusError;
  const handleStart = () => {
    if (
      rebuild &&
      !window.confirm(
        "确认重建当前项目的照片库索引？\n\n旧照片记录、EXIF metadata、AI 标签、向量和人脸关联将被清除并重新扫描；原始照片不会被删除。",
      )
    ) {
      return;
    }
    onStart(rebuild);
    setRebuild(false);
  };

  return (
    <div className="bg-canvas border border-hairline rounded-md p-4 space-y-3">
      {/* Title row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {status.running ? (
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
          ) : status.message === "cancelled" ? (
            <XCircle className="w-4 h-4 text-mute" />
          ) : status.message === "done" && !hasScanErrors ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : showError || hasScanErrors ? (
            <AlertCircle className="w-4 h-4 text-amber-500" />
          ) : (
            <FolderSearch className="w-4 h-4 text-mute" />
          )}
          <span className="text-body-sm font-semibold text-ink">{displayLabel}</span>
        </div>

        {status.running && onCancel && (
          <button
            onClick={onCancel}
            disabled={isCancelPending}
            className="text-btn-sm font-bold text-danger hover:text-red-800 disabled:text-stone transition-colors"
          >
            {isCancelPending ? "取消中…" : "取消任务"}
          </button>
        )}

        {!status.running && (
          <div className="flex flex-wrap items-center justify-end gap-3">
            {onReindex && (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => onReindex("missing_metadata")}
                    disabled={isReindexPending || isPending}
                    title="仅对缺少拍摄日期的照片重新提取 EXIF 元数据"
                    className="text-btn-sm font-bold text-secondary hover:text-ink disabled:text-stone transition-colors"
                  >
                    {isReindexPending ? "处理中…" : "补全元数据"}
                  </button>
                  <button
                    onClick={() => onReindex("all")}
                    disabled={isReindexPending || isPending}
                    title="对所有照片重新提取 EXIF 元数据"
                    className="text-caption-sm text-mute hover:text-ink disabled:text-stone transition-colors px-1"
                  >
                    (全部)
                  </button>
                </div>
                <button
                  onClick={() => onReindex("missing_location")}
                  disabled={isReindexPending || isPending}
                  title="仅对已有 GPS 但缺少地点名的照片补全地点信息"
                  className="text-btn-sm font-bold text-emerald-700 hover:text-emerald-900 disabled:text-stone transition-colors"
                >
                  {isReindexPending ? "处理中…" : "补地点"}
                </button>
              </div>
            )}
            <button
              onClick={handleStart}
              disabled={isPending || isReindexPending}
              className="min-h-11 text-btn-sm font-bold text-primary transition-colors hover:text-primary-pressed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer disabled:text-stone"
            >
              {isPending ? "启动中…" : rebuild ? "重建并扫描" : "重新扫描"}
            </button>
          </div>
        )}
      </div>

      {!status.running && (
        <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-hairline bg-surface-soft px-3 py-2.5">
          <input
            type="checkbox"
            checked={rebuild}
            onChange={(event) => setRebuild(event.target.checked)}
            disabled={isPending || isReindexPending}
            className="mt-0.5 h-5 w-5 shrink-0 accent-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
          />
          <span className="space-y-0.5">
            <span className="block text-body-sm font-semibold text-ink">重建照片库索引</span>
            <span className="block text-caption-sm leading-relaxed text-mute">
              仅本次扫描生效。清除当前项目旧照片记录、metadata、AI 标签、向量和人脸关联后重新扫描；不会删除原始照片。
            </span>
          </span>
        </label>
      )}

      {/* Error alert */}
      {showError && (
        <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
          <p className="text-caption-sm text-red-700 break-all">{showError}</p>
        </div>
      )}

      {/* Current file */}
      {status.running && status.current_path && (
        <p className="text-caption-sm text-mute truncate">
          {status.current_path.split("/").pop()}
        </p>
      )}

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">当前阶段</p>
          <p className="text-body-sm font-semibold text-ink">{stageLabel ?? "-"}</p>
        </div>
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">已发现</p>
          <p className="text-body-sm font-semibold text-ink">{status.discovered_count ?? status.scanned}</p>
        </div>
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">已预处理</p>
          <p className="text-body-sm font-semibold text-ink">{status.prepared_count ?? 0}</p>
        </div>
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">已落库</p>
          <p className="text-body-sm font-semibold text-ink">{status.persisted_count ?? 0}</p>
        </div>
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">队列积压</p>
          <p className="text-body-sm font-semibold text-ink">{status.queue_depth ?? 0}</p>
        </div>
        <div className="rounded-md border border-hairline bg-canvas px-3 py-2">
          <p className="text-caption-sm text-mute">最近阶段耗时</p>
          <p className="text-body-sm font-semibold text-ink">
            {typeof status.last_stage_latency_ms === "number" ? `${status.last_stage_latency_ms} ms` : "-"}
          </p>
        </div>
      </section>

      {recentFiles.length > 0 && (
        <section className="space-y-2 pt-1 border-t border-hairline">
          <div className="flex items-center gap-2">
            <FolderSearch className="w-4 h-4 text-primary" />
            <h3 className="text-body-sm font-semibold text-ink">最近文件进度</h3>
            <span className="text-caption-sm text-mute">{recentFiles.length} 条</span>
          </div>
          <div className="space-y-1.5 max-h-64 overflow-auto pr-1">
            {[...recentFiles].reverse().map((entry, index) => {
              const isFailed = entry.status === "failed";
              const fileName = entry.path.split("/").pop() || entry.path;
              return (
                <div
                  key={`${entry.timestamp}-${entry.path}-${index}`}
                  className="bg-canvas border border-hairline rounded-md px-4 py-2.5 space-y-0.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-body-sm text-ink truncate" title={entry.path}>
                      {fileName}
                    </p>
                    <span
                      className={[
                        "text-caption-sm font-medium whitespace-nowrap",
                        isFailed ? "text-danger" : "text-green-700",
                      ].join(" ")}
                    >
                      {isFailed ? "失败" : "成功"}
                    </span>
                  </div>
                  <p className="text-caption-sm text-mute break-all">{entry.path}</p>
                  {entry.message && (
                    <p className="text-caption-sm text-danger whitespace-pre-wrap break-all">
                      {entry.message}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      <ProjectTaskFailureDetails
        projectId={projectId}
        taskId={status.task_id}
        expectedCount={status.errors}
        title="扫描失败明细"
      />
    </div>
  );
}
