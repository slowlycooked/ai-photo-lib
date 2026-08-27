import type React from "react";
import { Link, NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  BrainCircuit,
  Bug,
  ChevronRight,
  ScanFace,
  Search,
  Settings2,
  SlidersHorizontal,
  UsersRound,
} from "lucide-react";

const globalNavItems = [
  { key: "general", label: "常规配置", to: "/settings/general", icon: SlidersHorizontal },
  { key: "ai-services", label: "AI 服务", to: "/settings/ai-services", icon: Bot },
  { key: "users", label: "用户管理", to: "/settings/users", icon: UsersRound },
  { key: "monitoring", label: "系统监控", to: "/settings/monitoring", icon: Activity },
  { key: "debug", label: "Debug / 日志", to: "/settings/debug", icon: Bug },
] as const;

const projectNavItems = [
  { key: "vision-ai", label: "视觉 AI", suffix: "vision-ai", icon: ScanFace },
  { key: "embedding-ai", label: "Embedding AI", suffix: "embedding-ai", icon: BrainCircuit },
  { key: "planner-ai", label: "Planner AI", suffix: "planner-ai", icon: Settings2 },
  { key: "advanced", label: "高级搜索参数", suffix: "advanced", icon: Search },
] as const;

function navClass(isActive: boolean) {
  return [
    "group flex min-w-0 items-center gap-3 rounded-xl border px-3 py-2.5 text-body-sm transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2",
    isActive
      ? "border-primary/25 bg-primary/10 text-primary font-semibold"
      : "border-transparent text-ink hover:border-hairline hover:bg-surface-card",
  ].join(" ");
}

function SettingsSidebar({ projectId }: { projectId: number | null }) {
  const projectSettingsBase = projectId != null ? `/projects/${projectId}/settings` : null;

  return (
    <aside className="h-fit space-y-5 rounded-2xl border border-hairline bg-canvas p-3 shadow-sm lg:sticky lg:top-20">
      <div>
        <p className="px-3 pb-2 text-caption-sm font-medium text-mute">系统</p>
        <nav className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-1" aria-label="基础设置">
          {globalNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.key} to={item.to} className={({ isActive }) => navClass(isActive)}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2 px-3 pb-2">
          <p className="text-caption-sm font-medium text-mute">项目 AI</p>
          <span className="rounded-full bg-secondary-bg px-2 py-0.5 text-caption-sm font-medium text-mute">
            {projectId != null ? `#${projectId}` : "未选择"}
          </span>
        </div>
        <nav className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-1" aria-label="AI 能力设置">
          {projectNavItems.map((item) => {
            const Icon = item.icon;
            if (projectSettingsBase == null) {
              return (
                <span
                  key={item.key}
                  aria-disabled="true"
                  title="请先选择项目"
                  className="flex min-w-0 items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 text-body-sm text-mute opacity-60"
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 truncate">{item.label}</span>
                </span>
              );
            }

            return (
              <NavLink
                key={item.key}
                to={`${projectSettingsBase}/${item.suffix}`}
                className={({ isActive }) => navClass(isActive)}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}

export function SettingsLayout({
  title,
  subtitle,
  currentProjectId,
  headerAction,
  showProjectSettingsLink = true,
  children,
}: {
  title: string;
  subtitle?: React.ReactNode;
  currentProjectId: number | null;
  headerAction?: React.ReactNode;
  showProjectSettingsLink?: boolean;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-4 py-5 sm:px-6 sm:py-7">
      <header className="flex flex-col gap-4 rounded-2xl border border-hairline bg-canvas p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Settings2 className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-md font-semibold text-ink">{title}</h1>
            {subtitle && <div className="mt-1 max-w-2xl text-caption-sm text-mute">{subtitle}</div>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          <div className="flex h-10 items-center gap-2 rounded-xl bg-secondary-bg px-3 text-body-sm">
            <span className="text-mute">当前项目</span>
            <span className="font-semibold tabular-nums text-ink">
              {currentProjectId != null ? `#${currentProjectId}` : "未选择"}
            </span>
          </div>
          {currentProjectId != null && showProjectSettingsLink && (
            <Link
              to={`/projects/${currentProjectId}/settings/vision-ai`}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-hairline px-3 text-body-sm font-medium text-ink transition-colors hover:bg-surface-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2"
            >
              项目设置
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          )}
          {headerAction}
        </div>
      </header>

      <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[248px_minmax(0,1fr)]">
        <SettingsSidebar projectId={currentProjectId} />
        <section className="min-w-0 space-y-5" aria-label="设置内容">{children}</section>
      </div>
    </main>
  );
}
