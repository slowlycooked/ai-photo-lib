import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SearchResultGrid } from "@/components/SearchResultGrid";
import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { SearchX, Bug, Tag } from "lucide-react";
import { useProjectContext } from "@/contexts/ProjectContext";
import type { SearchMode, TagField } from "@/api/types";
import { CAPABILITY_MATURITY } from "@/lib/capabilityMaturity";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "auto", label: "自动 / 按项目设置" },
  { value: "hybrid", label: "Hybrid" },
  { value: "keyword", label: "关键词" },
  { value: "vector", label: "语义 Vector" },
];

const TAG_FIELD_LABELS: Record<string, string> = {
  scene_tags: "场景标签",
  object_tags: "物体标签",
  activity_tags: "活动标签",
  quality_tags: "质量标签",
  search_keywords: "搜索关键词",
  location_clues: "位置线索",
};

type PeopleFilter = "all" | "group" | "solo" | "review" | "unnamed";

const PEOPLE_FILTERS: Array<{ value: PeopleFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "group", label: "合照" },
  { value: "solo", label: "单人照" },
  { value: "review", label: "待确认" },
  { value: "unnamed", label: "未命名人物" },
];

export function SearchPage() {
  const [params] = useSearchParams();
  const query = params.get("q") ?? "";
  const filter = params.get("filter");
  const tagField = params.get("tag_field") as TagField | null;
  const tagValue = params.get("tag_value");
  const { currentProjectId } = useProjectContext();
  const [mode, setMode] = useState<SearchMode>("auto");
  const [debug, setDebug] = useState(false);
  const [peopleFilter, setPeopleFilter] = useState<PeopleFilter>("all");

  const isTagFilter = filter === "tag" && tagField != null && tagValue != null;

  if (!query && !isTagFilter) {
    return (
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-24 flex flex-col items-center gap-4 text-mute">
        <SearchX className="w-10 h-10" />
        <p className="text-body-sm">在顶部搜索框输入关键词开始搜索</p>
      </main>
    );
  }

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-4">
      {isTagFilter ? (
        /* Tag filter mode header */
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-mute" />
            <span className="text-body-sm text-mute">
              {tagField ? TAG_FIELD_LABELS[tagField] ?? tagField : "标签"}：
            </span>
            <span className="px-2.5 py-1 rounded-full bg-primary/10 text-primary text-body-sm font-medium">
              {tagValue}
            </span>
          </div>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={debug}
              onChange={(e) => setDebug(e.target.checked)}
              className="rounded"
            />
            <Bug className="w-3.5 h-3.5" />
            Debug
          </label>
        </div>
      ) : (
        /* Normal search mode header */
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center rounded-md border border-border overflow-hidden text-sm">
            {MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => setMode(m.value)}
                className={
                  "px-3 py-1.5 transition-colors " +
                  (mode === m.value
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-accent text-muted-foreground")
                }
              >
                {m.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={debug}
              onChange={(e) => setDebug(e.target.checked)}
              className="rounded"
            />
            <Bug className="w-3.5 h-3.5" />
            Debug
          </label>
          <div className="flex items-center rounded-md border border-border overflow-hidden text-sm">
            {PEOPLE_FILTERS.map((item) => (
              <button
                key={item.value}
                onClick={() => setPeopleFilter(item.value)}
                className={
                  "px-3 py-1.5 transition-colors " +
                  (peopleFilter === item.value
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-accent text-muted-foreground")
                }
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="text-caption-sm text-mute flex flex-wrap items-center gap-2">
            <CapabilityMaturityBadge item={CAPABILITY_MATURITY.search_face_filters} compact />
            <span>{CAPABILITY_MATURITY.search_face_filters.hint}</span>
          </p>
        </div>
      )}

      <SearchResultGrid
        query={isTagFilter ? "" : query}
        projectId={currentProjectId}
        mode={mode}
        debug={debug}
        tagField={isTagFilter ? tagField : undefined}
        tagValue={isTagFilter ? tagValue : undefined}
        faceCountMin={peopleFilter === "group" ? 2 : peopleFilter === "solo" ? 1 : undefined}
        faceCountMax={peopleFilter === "solo" ? 1 : undefined}
        hasReviewPending={peopleFilter === "review" ? true : undefined}
        hasUnnamedPeople={peopleFilter === "unnamed" ? true : undefined}
      />
    </main>
  );
}
