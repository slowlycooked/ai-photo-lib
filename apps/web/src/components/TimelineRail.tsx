import { useTimeline } from "@/hooks/usePhotos";
import type { FolderScope } from "@/api";

interface TimelineRailProps {
  projectId?: number | null;
  folderId?: number | null;
  folderScope?: FolderScope;
  activeKey?: string | null;
  onSelect: (key: string, dateFrom: string, dateTo: string) => void;
}

export function TimelineRail({ projectId, folderId, folderScope = "subtree", activeKey, onSelect }: TimelineRailProps) {
  const { data, isLoading } = useTimeline(projectId, folderId, folderScope);

  if (isLoading || !data?.items.length) return null;

  // Group by year
  const byYear = new Map<number, typeof data.items>();
  for (const item of data.items) {
    const bucket = byYear.get(item.year) ?? [];
    bucket.push(item);
    byYear.set(item.year, bucket);
  }

  const years = [...byYear.keys()].sort((a, b) => b - a);

  return (
    <nav
      className="hidden xl:flex flex-col gap-0.5 sticky top-20 max-h-[calc(100vh-5rem)] overflow-y-auto pr-1 pb-4 text-right min-w-[80px]"
      aria-label="时间线"
    >
      {years.map((year) => {
        const months = byYear.get(year)!;
        return (
          <div key={year} className="mb-2">
            <p className="text-caption-sm font-bold text-mute mb-1 pr-1">{year}</p>
            {months.map((item) => {
              const isActive = item.key === activeKey;
              // date_from = first day of month, date_to = first day of next month
              const dateFrom = `${item.year}-${String(item.month).padStart(2, "0")}-01`;
              const nextMonth = item.month === 12 ? 1 : item.month + 1;
              const nextYear = item.month === 12 ? item.year + 1 : item.year;
              const dateTo = `${nextYear}-${String(nextMonth).padStart(2, "0")}-01`;

              return (
                <button
                  key={item.key}
                  onClick={() => onSelect(item.key, dateFrom, dateTo)}
                  className={[
                    "w-full flex items-center justify-between gap-2 px-1.5 py-0.5 rounded",
                    "text-right text-caption-sm transition-colors",
                    isActive
                      ? "bg-secondary-bg text-ink font-semibold"
                      : "text-mute hover:text-ink hover:bg-surface-card",
                  ].join(" ")}
                  title={`${item.year}年${item.month}月 — ${item.count} 张`}
                >
                  <span className="text-caption-sm tabular-nums text-ash">
                    {item.count}
                  </span>
                  <span>{item.month}月</span>
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
