import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2, Tag, AlertCircle } from "lucide-react";
import { api, type TagCount } from "@/lib/api";
import { useProjectContext } from "@/contexts/ProjectContext";

const SECTIONS = [
  { key: "scene_tags" as const, label: "场景标签", color: "bg-blue-50 text-blue-700 hover:bg-blue-100" },
  { key: "object_tags" as const, label: "物体标签", color: "bg-green-50 text-green-700 hover:bg-green-100" },
  { key: "activity_tags" as const, label: "活动标签", color: "bg-purple-50 text-purple-700 hover:bg-purple-100" },
  { key: "quality_tags" as const, label: "质量标签", color: "bg-amber-50 text-amber-700 hover:bg-amber-100" },
  { key: "search_keywords" as const, label: "搜索关键词", color: "bg-primary/10 text-primary hover:bg-primary/20" },
] as const;

function TagChip({
  tag,
  count,
  color,
  onClick,
}: {
  tag: string;
  count: number;
  color: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-caption-md font-medium transition-colors cursor-pointer",
        color,
      ].join(" ")}
    >
      {tag}
      <span className="opacity-60 text-caption-sm tabular-nums">{count}</span>
    </button>
  );
}

function TagSection({
  title,
  tags,
  color,
  onTagClick,
}: {
  title: string;
  tags: TagCount[];
  color: string;
  onTagClick: (tag: string) => void;
}) {
  if (tags.length === 0) return null;
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Tag className="w-4 h-4 text-mute" />
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
        <span className="text-caption-sm text-mute">{tags.length} 个</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {tags.map(({ tag, count }) => (
          <TagChip
            key={tag}
            tag={tag}
            count={count}
            color={color}
            onClick={() => onTagClick(tag)}
          />
        ))}
      </div>
    </section>
  );
}

export function TagsPage() {
  const navigate = useNavigate();
  const { currentProjectId } = useProjectContext();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["tags", currentProjectId],
    queryFn: () => currentProjectId !== null ? api.projects.tags(currentProjectId) : Promise.resolve(null),
    enabled: currentProjectId !== null,
    staleTime: 60_000,
  });

  const handleTagClick = (tag: string) => {
    navigate(`/search?q=${encodeURIComponent(tag)}`);
  };

  const totalTags = data
    ? SECTIONS.reduce((sum, s) => sum + data[s.key].length, 0)
    : 0;

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-heading-md font-semibold text-ink">标签浏览</h1>
        {data && (
          <p className="text-body-sm text-mute">共 {totalTags} 种标签</p>
        )}
      </div>

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p className="text-body-sm">加载标签中…</p>
        </div>
      )}

      {isError && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
          <AlertCircle className="w-8 h-8" />
          <p className="text-body-sm">无法加载标签，请检查 API 服务</p>
        </div>
      )}

      {data && totalTags === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-4 text-mute">
          <div className="w-20 h-20 rounded-full bg-secondary-bg flex items-center justify-center">
            <Tag className="w-9 h-9 text-stone" />
          </div>
          <div className="text-center">
            <p className="text-heading-md font-semibold text-ink">还没有标签</p>
            <p className="text-body-sm text-mute mt-1">先在「任务」页面启动 AI 分析，标签将自动生成</p>
          </div>
        </div>
      )}

      {data &&
        SECTIONS.map(({ key, label, color }) => (
          <TagSection
            key={key}
            title={label}
            tags={data[key]}
            color={color}
            onTagClick={handleTagClick}
          />
        ))}
    </main>
  );
}
