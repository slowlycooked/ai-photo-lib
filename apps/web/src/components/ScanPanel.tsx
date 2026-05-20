import { CheckCircle2, Loader2, AlertCircle, FolderSearch } from "lucide-react";
import type { ScanStatus } from "@/lib/api";

// Messages that are normal lifecycle states, not errors.
const LABEL: Record<string, string> = {
  idle: "待扫描",
  scanning: "正在扫描照片目录…",
  done: "扫描完成",
  done_with_errors: "扫描完成（含错误）",
};

interface ScanPanelProps {
  status: ScanStatus | undefined;
  isLoading: boolean;
  onStart: () => void;
  isPending: boolean;
  /** Network / API-level error from the start-scan mutation. */
  mutationError?: string | null;
}

export function ScanPanel({ status, isLoading, onStart, isPending, mutationError }: ScanPanelProps) {
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

  const displayLabel = status.running
    ? LABEL.scanning
    : LABEL[status.message] ?? status.message;

  const showError = mutationError ?? statusError;

  return (
    <div className="bg-canvas border border-hairline rounded-md p-4 space-y-3">
      {/* Title row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {status.running ? (
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
          ) : status.message === "done" ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : showError || status.errors > 0 ? (
            <AlertCircle className="w-4 h-4 text-amber-500" />
          ) : (
            <FolderSearch className="w-4 h-4 text-mute" />
          )}
          <span className="text-body-sm font-semibold text-ink">{displayLabel}</span>
        </div>

        {!status.running && (
          <button
            onClick={onStart}
            disabled={isPending}
            className="text-btn-sm font-bold text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
          >
            {isPending ? "启动中…" : "重新扫描"}
          </button>
        )}
      </div>

      {/* Error alert */}
      {showError && (
        <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
          <p className="text-caption-sm text-red-700 break-all">{showError}</p>
        </div>
      )}

      {/* Stats */}
      {status.scanned > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <Stat label="已扫描" value={status.scanned} />
          <Stat label="新增" value={status.inserted} accent />
          <Stat label="更新" value={status.updated} />
          <Stat label="错误" value={status.errors} warn={status.errors > 0} />
        </div>
      )}

      {/* Current file */}
      {status.running && status.current_path && (
        <p className="text-caption-sm text-mute truncate">
          {status.current_path.split("/").pop()}
        </p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  warn,
}: {
  label: string;
  value: number;
  accent?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="text-center">
      <p
        className={[
          "text-heading-md font-semibold",
          accent ? "text-primary" : warn ? "text-amber-600" : "text-ink",
        ].join(" ")}
      >
        {value.toLocaleString()}
      </p>
      <p className="text-caption-sm text-mute mt-0.5">{label}</p>
    </div>
  );
}
