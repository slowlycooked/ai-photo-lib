import { CheckCircle2, Loader2 } from "lucide-react";

import {
  buildTaskStatusViewModel,
  stateColorClass,
  type QueueTaskStatus,
} from "@/lib/projectTasksViewModel";

function StatTile({
  label,
  value,
  color = "text-ink",
}: {
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <div className="bg-canvas border border-hairline rounded-md px-4 py-3 text-center">
      <p className={`text-heading-md font-bold tabular-nums ${color}`}>{value}</p>
      <p className="text-caption-sm text-mute mt-0.5">{label}</p>
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

  return (
    <>
      <div className="flex items-center gap-2">
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin text-mute" />
        ) : viewModel.state === "running" ? (
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
        ) : (
          <CheckCircle2 className={`w-4 h-4 ${stateColorClass(viewModel.state)}`} />
        )}
        <h2 className="text-body-sm font-semibold text-ink">{viewModel.title}</h2>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <StatTile label="排队中" value={viewModel.counts.queued} />
        <StatTile
          label="进行中"
          value={viewModel.counts.running}
          color={viewModel.counts.running > 0 ? "text-primary" : "text-ink"}
        />
        <StatTile label="已完成" value={viewModel.counts.success} color="text-green-700" />
        <StatTile
          label="失败"
          value={viewModel.counts.failed}
          color={viewModel.counts.failed > 0 ? "text-amber-600" : "text-ink"}
        />
        <StatTile label="总计" value={viewModel.counts.total} />
      </div>

      <p className="text-caption-sm text-mute">{viewModel.message}</p>
    </>
  );
}
