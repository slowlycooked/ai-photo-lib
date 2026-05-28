import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";

export function ProjectTaskFailureDetails({
  projectId,
  taskId,
  expectedCount = 0,
  title = "失败明细",
  emptyText = "没有失败明细。",
  compact = false,
}: {
  projectId: number | null;
  taskId: number | null | undefined;
  expectedCount?: number;
  title?: string;
  emptyText?: string;
  compact?: boolean;
}) {
  const [limit, setLimit] = useState(20);

  useEffect(() => {
    setLimit(20);
  }, [projectId, taskId]);

  const shouldLoad = projectId != null && taskId != null && expectedCount > 0;
  const query = useQuery({
    queryKey: queryKeys.projectTaskFailures(projectId, taskId ?? null, limit, 0),
    queryFn: () => api.projects.taskFailures(projectId!, taskId!, { limit, offset: 0 }),
    enabled: shouldLoad,
  });

  if (expectedCount <= 0) return null;
  if (taskId == null) {
    return <p className="text-caption-sm text-mute">失败明细暂不可用。</p>;
  }
  if (query.isLoading) {
    return <p className="text-caption-sm text-mute">正在加载失败明细…</p>;
  }
  if (query.error instanceof Error) {
    return <p className="text-caption-sm text-danger">失败明细加载失败：{query.error.message}</p>;
  }

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? expectedCount;
  if (total === 0) {
    return <p className="text-caption-sm text-mute">{emptyText}</p>;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-caption-sm font-medium text-danger">{title}</p>
        <span className="text-caption-sm text-mute">{items.length}/{total}</span>
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className={[
              "rounded-md border border-rose-200 bg-rose-50 px-3 py-2 space-y-1",
              compact ? "text-caption-sm" : "",
            ].join(" ")}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-caption-sm font-medium text-rose-900">{item.message}</p>
              <span className="text-caption-sm text-rose-700">{item.source}</span>
            </div>
            {item.path && <p className="text-caption-sm text-rose-800 break-all">path={item.path}</p>}
            <p className="text-caption-sm text-rose-700">
              status={item.status ?? "-"} · time={formatTaskTime(item.timestamp)}
            </p>
            {item.details && Object.keys(item.details).length > 0 && (
              <pre className="max-h-40 overflow-auto rounded-md bg-white/70 border border-rose-100 px-3 py-2 text-caption-sm text-rose-900 whitespace-pre-wrap break-all">
                {formatTaskJson(item.details)}
              </pre>
            )}
          </div>
        ))}
      </div>
      {total > items.length && (
        <button
          type="button"
          onClick={() => setLimit((value) => value + 20)}
          className="inline-flex items-center gap-1 rounded-md border border-hairline px-3 py-1.5 text-caption-sm font-medium text-secondary hover:text-ink transition-colors"
        >
          加载更多失败明细
        </button>
      )}
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

function formatTaskTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}