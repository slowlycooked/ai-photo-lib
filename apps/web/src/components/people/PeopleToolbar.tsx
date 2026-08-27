import { Archive, ChevronDown, GitMerge, Search, Trash2, UserPlus } from "lucide-react";
import type { PeopleFilterMode } from "@/hooks/usePeoplePage";
import type { PersonSummary } from "@/api";

export function PeopleToolbar({
  filterMode,
  setFilterMode,
  searchText,
  setSearchText,
  createDisplayName,
  setCreateDisplayName,
  actionBusy,
  onCreatePerson,
  hasSelectedPerson,
  selectedPersonCount,
  moveCandidates,
  mergeTargetId,
  setMergeTargetId,
  onMergeSelectedPerson,
  onArchiveSelectedPerson,
  onArchiveSelectedPeople,
  onDeleteSelectedPerson,
}: {
  filterMode: PeopleFilterMode;
  setFilterMode: (mode: PeopleFilterMode) => void;
  searchText: string;
  setSearchText: (value: string) => void;
  createDisplayName: string;
  setCreateDisplayName: (value: string) => void;
  actionBusy: boolean;
  onCreatePerson: () => void;
  hasSelectedPerson: boolean;
  selectedPersonCount: number;
  moveCandidates: PersonSummary[];
  mergeTargetId: number | null;
  setMergeTargetId: (personId: number) => void;
  onMergeSelectedPerson: () => void;
  onArchiveSelectedPerson: () => void;
  onArchiveSelectedPeople: () => void;
  onDeleteSelectedPerson: () => void;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-hairline bg-canvas" aria-label="人物筛选与管理">
      <div className="grid gap-2 p-3 sm:grid-cols-[160px_minmax(220px,1fr)] xl:grid-cols-[160px_minmax(260px,1fr)_minmax(320px,auto)]">
          <label>
            <span className="sr-only">筛选人物</span>
            <select
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value as PeopleFilterMode)}
              aria-label="筛选人物"
              className="min-h-11 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
            >
              <option value="all">全部</option>
              <option value="named">已命名</option>
              <option value="unnamed">未命名</option>
              <option value="review_pending">有待确认</option>
              <option value="auto_assigned">自动识别样本&gt;0</option>
            </select>
          </label>

          <label>
            <span className="sr-only">搜索</span>
            <span className="flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 focus-within:ring-2 focus-within:ring-focus-outer">
              <Search className="h-4 w-4 shrink-0 text-mute" aria-hidden="true" />
              <input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="按人物名搜索"
                className="min-w-0 flex-1 bg-transparent text-body-sm text-ink outline-none placeholder:text-mute"
              />
            </span>
          </label>

        <div className="flex min-w-0 gap-2 sm:col-span-2 xl:col-span-1">
          <label className="min-w-0 flex-1">
            <span className="sr-only">新建人物</span>
            <input
              value={createDisplayName}
              onChange={(e) => setCreateDisplayName(e.target.value)}
              placeholder="新人物名称（可为空）"
              className="min-h-11 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
            />
          </label>
          <button
            type="button"
            disabled={actionBusy}
            onClick={onCreatePerson}
            className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-btn-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
          >
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            创建人物
          </button>
        </div>
      </div>

      {(hasSelectedPerson || selectedPersonCount > 0) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-hairline bg-surface-soft px-3 py-2">
          {selectedPersonCount > 0 && (
            <>
              <span className="text-caption-sm font-medium text-primary">已选择 {selectedPersonCount} 人</span>
              <button
                type="button"
                disabled={actionBusy}
                onClick={onArchiveSelectedPeople}
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
              >
                <Archive className="h-4 w-4" aria-hidden="true" />
                批量加入 archive（{selectedPersonCount}）
              </button>
            </>
          )}

          {hasSelectedPerson && (
            <details className="group ml-auto w-full max-w-full sm:w-auto">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-secondary hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer [&::-webkit-details-marker]:hidden">
                管理当前人物
                <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
              </summary>
              <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
                {moveCandidates.length > 0 && (
                  <>
                    <select
                      value={mergeTargetId != null ? String(mergeTargetId) : ""}
                      onChange={(e) => setMergeTargetId(Number(e.target.value))}
                      aria-label="合并目标人物"
                      className="min-h-11 min-w-0 rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
                    >
                      {moveCandidates.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          合并到：{candidate.display_name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      disabled={actionBusy}
                      onClick={onMergeSelectedPerson}
                      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                    >
                      <GitMerge className="h-4 w-4" aria-hidden="true" />
                      合并当前人物
                    </button>
                  </>
                )}
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={onArchiveSelectedPerson}
                  className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                >
                  <Archive className="h-4 w-4" aria-hidden="true" />
                  加入 archive
                </button>
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={onDeleteSelectedPerson}
                  className="inline-flex min-h-11 items-center gap-2 rounded-md border border-danger/30 bg-canvas px-3 text-btn-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  删除人物
                </button>
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
