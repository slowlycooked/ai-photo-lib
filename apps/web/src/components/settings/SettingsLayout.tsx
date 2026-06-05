import type React from "react";
import { Link, NavLink } from "react-router-dom";

const globalNavItems = [
  { key: "general", label: "常规配置", to: "/settings/general" },
  { key: "ai-services", label: "AI 服务", to: "/settings/ai-services" },
  { key: "users", label: "用户管理", to: "/settings/users" },
  { key: "monitoring", label: "系统监控", to: "/settings/monitoring" },
  { key: "debug", label: "Debug / 日志", to: "/settings/debug" },
] as const;

const projectNavItems = [
  { key: "vision-ai", label: "视觉 AI", suffix: "vision-ai" },
  { key: "embedding-ai", label: "Embedding AI", suffix: "embedding-ai" },
  { key: "planner-ai", label: "Planner AI", suffix: "planner-ai" },
  { key: "advanced", label: "高级搜索参数", suffix: "advanced" },
] as const;

function navClass(isActive: boolean) {
  return [
    "flex items-center gap-2 px-6 py-3.5 rounded-[28px] text-[16px] leading-6 border transition-colors",
    isActive
      ? "border-primary text-primary bg-primary/10 font-semibold"
      : "border-transparent text-ink hover:bg-surface-card",
  ].join(" ");
}

function SettingsSidebar({ projectId }: { projectId: number | null }) {
  const projectSettingsBase = projectId != null ? `/projects/${projectId}/settings` : null;

  return (
    <aside className="bg-canvas border border-hairline rounded-[18px] px-4 py-5 h-fit space-y-5">
      <div>
        <p className="px-5 py-1 text-[15px] leading-5 text-mute">基础</p>
        <nav className="space-y-3 mt-2" aria-label="基础设置">
          {globalNavItems.map((item) => (
            <NavLink key={item.key} to={item.to} className={({ isActive }) => navClass(isActive)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div>
        <p className="px-5 py-1 text-[15px] leading-5 text-mute">AI 能力（项目级）</p>
        <nav className="space-y-3 mt-2" aria-label="AI 能力设置">
          {projectNavItems.map((item) => {
            if (projectSettingsBase == null) {
              return (
                <span
                  key={item.key}
                  className="flex items-center gap-2 px-6 py-3.5 rounded-[28px] text-[16px] leading-6 text-mute border border-transparent"
                >
                  {item.label}
                </span>
              );
            }

            return (
              <NavLink
                key={item.key}
                to={`${projectSettingsBase}/${item.suffix}`}
                className={({ isActive }) => navClass(isActive)}
              >
                {item.label}
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
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-heading-md font-semibold text-ink">{title}</h1>
          {subtitle && <div className="text-caption-sm text-mute mt-1">{subtitle}</div>}
        </div>
        {headerAction}
      </div>

      <div className="rounded-md border border-hairline bg-canvas px-4 py-3 flex flex-wrap items-center gap-3 text-body-sm">
        <span className="text-mute">当前项目</span>
        <span className="font-medium text-ink">{currentProjectId != null ? `#${currentProjectId}` : "未选择"}</span>
        {currentProjectId != null && showProjectSettingsLink && (
          <Link
            to={`/projects/${currentProjectId}/settings/vision-ai`}
            className="ml-auto px-3 py-1.5 rounded-md border border-hairline hover:bg-surface-card"
          >
            打开项目设置
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] gap-6">
        <SettingsSidebar projectId={currentProjectId} />
        <section className="space-y-6">{children}</section>
      </div>
    </main>
  );
}
