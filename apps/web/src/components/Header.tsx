import { useEffect, useMemo, useState } from "react";
import { Camera, Search, X, Images, Tag, ListTodo, Settings, Users, LogOut, Trash2 } from "lucide-react";
import { NavLink, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { ProjectSelector } from "./ProjectSelector";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useAuth } from "@/contexts/AuthContext";

export function Header() {
  const { currentProjectId } = useProjectContext();
  const auth = useAuth();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const navItems = useMemo(
    () => {
      const items = [
      { to: "/photos", label: "照片", icon: Images },
      {
        to: currentProjectId != null ? `/projects/${currentProjectId}/people` : "/photos",
        label: "人物",
        icon: Users,
      },
      { to: "/tags", label: "标签", icon: Tag },
      { to: "/tasks", label: "任务", icon: ListTodo },
      ];
      if (currentProjectId != null) {
        items.push({
          to: `/projects/${currentProjectId}/photo-quarantine`,
          label: "待删除",
          icon: Trash2,
        });
      }
      if (auth.session?.role === "admin") {
        items.push({ to: "/settings", label: "设置", icon: Settings });
      } else if (auth.session?.role === "project_manager" && currentProjectId != null) {
        items.push({
          to: `/projects/${currentProjectId}/settings/vision-ai`,
          label: "项目设置",
          icon: Settings,
        });
      }
      return items;
    },
    [auth.session?.role, currentProjectId],
  );

  // Pre-fill search input from URL when on /search
  const urlQuery = location.pathname === "/search" ? (params.get("q") ?? "") : "";
  const [input, setInput] = useState(urlQuery);

  useEffect(() => {
    if (location.pathname === "/search") {
      setInput(params.get("q") ?? "");
    } else {
      setInput("");
    }
  }, [location.pathname, params]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (q) navigate(`/search?q=${encodeURIComponent(q)}`);
  };

  const handleClear = () => {
    setInput("");
    if (location.pathname === "/search") navigate("/search");
  };

  const handleLogout = async () => {
    await auth.logout();
    navigate("/login", { replace: true });
  };

  const isSettingsRoute =
    location.pathname.startsWith("/settings") ||
    /^\/projects\/\d+\/settings(\/|$)/.test(location.pathname);

  return (
    <header className="sticky top-0 z-50 bg-canvas border-b border-hairline h-14 flex items-center px-4 sm:px-6 gap-3">
      {/* Logo */}
      <NavLink to="/photos" className="flex items-center gap-2 flex-shrink-0">
        <div className="w-7 h-7 bg-primary rounded-full flex items-center justify-center">
          <Camera className="w-4 h-4 text-white" strokeWidth={2.5} />
        </div>
        <span className="text-body-sm font-bold text-ink tracking-tight hidden md:block">
          AI Photo Library
        </span>
      </NavLink>

      {/* Project selector */}
      <ProjectSelector />

      {/* Nav links */}
      <nav className="hidden sm:flex items-center gap-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={`${label}:${to}`}
            to={to}
            className={({ isActive }) =>
              [
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-btn-sm transition-colors",
                isActive || (label === "设置" && isSettingsRoute)
                  ? "bg-secondary-bg text-ink font-bold"
                  : "text-mute hover:text-ink hover:bg-surface-card",
              ].join(" ")
            }
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="flex-1 max-w-md mx-auto">
        <div className="relative flex items-center">
          <Search className="absolute left-3 w-4 h-4 text-ash pointer-events-none" />
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="搜索：爬山、夜景、有文字的照片…"
            className={[
              "w-full pl-9 pr-9 py-1.5 rounded-full bg-surface-card text-body-sm text-ink",
              "placeholder:text-ash border border-hairline",
              "focus:outline-none focus:ring-2 focus:ring-focus-outer focus:border-transparent",
              "transition-shadow",
            ].join(" ")}
          />
          {input && (
            <button
              type="button"
              onClick={handleClear}
              className="absolute right-3 w-5 h-5 flex items-center justify-center rounded-full hover:bg-secondary-bg text-ash hover:text-ink transition-colors"
              aria-label="清除搜索"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </form>

      <button
        type="button"
        onClick={handleLogout}
        className="w-9 h-9 flex items-center justify-center rounded-sm text-mute hover:text-ink hover:bg-surface-card transition-colors"
        aria-label="退出登录"
        title="退出登录"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </header>
  );
}
