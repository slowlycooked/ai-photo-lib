import { ScanFace, Settings2, Users } from "lucide-react";
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
    <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Users className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-heading-lg font-semibold text-ink">人物</h1>
          <p className="text-body-sm text-mute">
            {projectName} · 共 {peopleCount} 个分组
          </p>
          <div className="mt-2 flex flex-wrap gap-2" aria-label={`已命名 ${namedCount} 人，未命名 ${unnamedCount} 人`}>
            <span className="rounded-full bg-success/10 px-2.5 py-0.5 text-caption-sm font-medium text-success">
              已命名 <strong className="tabular-nums">{namedCount}</strong>
            </span>
            <span className="rounded-full bg-secondary-bg px-2.5 py-0.5 text-caption-sm font-medium text-secondary">
              未命名 <strong className="tabular-nums">{unnamedCount}</strong>
            </span>
          </div>
        </div>
      </div>
      <nav className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto" aria-label="人物页面快捷入口">
        <Link
          to={`/projects/${projectId}/settings/vision-ai`}
          className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-secondary transition-colors hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
        >
          <Settings2 className="h-4 w-4" aria-hidden="true" />
          AI 设置
        </Link>
        <Link
          to={`/projects/${projectId}/people/review`}
          className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-btn-sm font-semibold text-white transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
        >
          <ScanFace className="h-4 w-4" aria-hidden="true" />
          审核人脸
        </Link>
      </nav>
    </header>
  );
}
