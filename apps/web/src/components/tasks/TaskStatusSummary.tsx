import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
} from "lucide-react";

import {
  buildTaskStatusViewModel,
  stateColorClass,
  type QueueTaskStatus,
} from "@/lib/projectTasksViewModel";

function StatItem({
  icon,
  label,
  value,
  color = "text-ink",
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <div className="min-w-0 rounded-sm bg-surface-soft px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-caption-sm text-mute">
        {icon}
        <span>{label}</span>
      </div>
      <p className={`mt-1 text-heading-md font-bold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

export function TaskStatusSummary({
  status,
  idleTitle,
  runningTitle,
  noun,
  loading,
}: {
  status: QueueTaskStatus | null | undefined;
  idleTitle: string;
  runningTitle: string;
  noun: string;
  loading?: boolean;
}) {
  const viewModel = buildTaskStatusViewModel(status, {
    idleTitle,
    runningTitle,
    noun,
  });
  const completionRate = viewModel.counts.total > 0
    ? Math.min(
        100,
        Math.max(0, Math.round((viewModel.counts.success / viewModel.counts.total) * 1000) / 10)
      )
    : 0;
  const completionLabel = Number.isInteger(completionRate)
    ? `${completionRate.toFixed(0)}%`
    : `${completionRate.toFixed(1)}%`;

  return (
    <section className="rounded-md border border-hairline bg-canvas p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {loading ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-mute" aria-hidden="true" />
          ) : viewModel.state === "running" ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" aria-hidden="true" />
          ) : (
            <CheckCircle2
              className={`h-4 w-4 shrink-0 ${stateColorClass(viewModel.state)}`}
              aria-hidden="true"
            />
          )}
          <div className="min-w-0">
            <h2 className="text-body-sm font-semibold text-ink">{viewModel.title}</h2>
            <p className="text-caption-sm text-mute">{viewModel.message}</p>
          </div>
        </div>
        <span className="text-caption-sm tabular-nums text-mute">
          共 {viewModel.counts.total.toLocaleString()} {noun}
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-[144px_minmax(0,1fr)] sm:items-center">
        <div
          className="relative mx-auto grid h-32 w-32 place-items-center"
          role="img"
          aria-label={`完成率 ${completionLabel}，已完成 ${viewModel.counts.success}，总计 ${viewModel.counts.total}`}
        >
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 120 120" aria-hidden="true">
            <circle
              cx="60"
              cy="60"
              r="48"
              fill="none"
              stroke="currentColor"
              strokeWidth="10"
              className="text-secondary-bg"
            />
            <circle
              cx="60"
              cy="60"
              r="48"
              pathLength="100"
              fill="none"
              stroke="currentColor"
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={`${completionRate} ${100 - completionRate}`}
              transform="rotate(-90 60 60)"
              className={viewModel.counts.failed > 0 ? "text-amber-600" : "text-green-700"}
            />
          </svg>
          <div className="relative text-center">
            <p className="text-heading-lg font-bold tabular-nums text-ink">{completionLabel}</p>
            <p className="text-caption-sm text-mute">完成率</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatItem
            icon={<Clock3 className="h-3.5 w-3.5" aria-hidden="true" />}
            label="排队中"
            value={viewModel.counts.queued.toLocaleString()}
          />
          <StatItem
            icon={<Activity className="h-3.5 w-3.5" aria-hidden="true" />}
            label="进行中"
            value={viewModel.counts.running.toLocaleString()}
            color={viewModel.counts.running > 0 ? "text-primary" : "text-ink"}
          />
          <StatItem
            icon={<CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
            label="已完成"
            value={viewModel.counts.success.toLocaleString()}
            color="text-green-700"
          />
          <StatItem
            icon={<AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
            label="失败"
            value={viewModel.counts.failed.toLocaleString()}
            color={viewModel.counts.failed > 0 ? "text-amber-600" : "text-ink"}
          />
        </div>
      </div>
    </section>
  );
}
