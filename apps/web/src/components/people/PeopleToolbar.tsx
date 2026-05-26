import { GitMerge, Search, Trash2, UserPlus } from "lucide-react";
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
  moveCandidates,
  mergeTargetId,
  setMergeTargetId,
  onMergeSelectedPerson,
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
  moveCandidates: PersonSummary[];
  mergeTargetId: number | null;
  setMergeTargetId: (personId: number) => void;
  onMergeSelectedPerson: () => void;
  onDeleteSelectedPerson: () => void;
}) {
  return (
    <div className="bg-canvas border border-hairline rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-caption-sm text-mute">筛选</label>
        <select
          value={filterMode}
          onChange={(e) => setFilterMode(e.target.value as PeopleFilterMode)}
          className="px-2 py-1 rounded-md border border-hairline bg-canvas text-caption-sm"
        >
          <option value="all">全部</option>
          <option value="named">已命名</option>
          <option value="unnamed">未命名</option>
          <option value="review_pending">有待确认</option>
          <option value="auto_assigned">自动识别样本&gt;0</option>
        </select>

        <label className="text-caption-sm text-mute ml-2">搜索</label>
        <div className="flex items-center gap-1 px-2 py-1 rounded-md border border-hairline bg-canvas">
          <Search className="w-3.5 h-3.5 text-mute" />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="按人物名搜索"
            className="bg-transparent text-caption-sm outline-none"
          />
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={createDisplayName}
          onChange={(e) => setCreateDisplayName(e.target.value)}
          placeholder="新人物名称（可为空）"
          className="px-3 py-1.5 rounded-md border border-hairline bg-canvas text-caption-sm"
        />
        <button
          type="button"
          disabled={actionBusy}
          onClick={onCreatePerson}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
        >
          <UserPlus className="w-3.5 h-3.5" />
          创建人物
        </button>

        {hasSelectedPerson && moveCandidates.length > 0 && (
          <>
            <select
              value={mergeTargetId != null ? String(mergeTargetId) : ""}
              onChange={(e) => setMergeTargetId(Number(e.target.value))}
              className="px-2 py-1 rounded-md border border-hairline bg-canvas text-caption-sm"
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
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
            >
              <GitMerge className="w-3.5 h-3.5" />
              合并当前人物
            </button>
          </>
        )}

        {hasSelectedPerson && (
          <button
            type="button"
            disabled={actionBusy}
            onClick={onDeleteSelectedPerson}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-caption-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            删除人物
          </button>
        )}
      </div>
    </div>
  );
}
