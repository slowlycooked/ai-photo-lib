import { Link } from "react-router-dom";

export function PeopleHeader({
  projectId,
  projectName,
  peopleCount,
  namedCount,
  unnamedCount,
}: {
  projectId: number;
  projectName: string;
  peopleCount: number;
  namedCount: number;
  unnamedCount: number;
}) {
  return (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-heading-md font-semibold text-ink">人物</h1>
        <p className="text-body-sm text-mute mt-1">
          项目：{projectName} · 共 {peopleCount} 个分组
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 text-caption-md">
          已命名 {namedCount}
        </span>
        <span className="px-3 py-1 rounded-full bg-secondary-bg text-mute text-caption-md">
          未命名 {unnamedCount}
        </span>
        <Link
          to={`/projects/${projectId}/settings/ai`}
          className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
        >
          打开 AI / Face 配置
        </Link>
        <Link
          to={`/projects/${projectId}/people/review`}
          className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
        >
          打开 Review 页
        </Link>
      </div>
    </div>
  );
}
