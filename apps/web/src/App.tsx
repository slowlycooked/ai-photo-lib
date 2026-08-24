import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Header } from "@/components/Header";
import { PhotosPage } from "@/pages/PhotosPage";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { api } from "@/api";
import { configureFrontendLogger, logger } from "@/lib/logger";
import { LegacyScanRouteRedirect } from "@/components/LegacyScanRouteRedirect";

const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const SearchPage = lazy(() =>
  import("@/pages/SearchPage").then((module) => ({ default: module.SearchPage })),
);
const TagsPage = lazy(() =>
  import("@/pages/TagsPage").then((module) => ({ default: module.TagsPage })),
);
const TasksPage = lazy(() =>
  import("@/pages/TasksPage").then((module) => ({ default: module.TasksPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const ProjectAISettingsPage = lazy(() =>
  import("@/pages/ProjectAISettingsPage").then((module) => ({
    default: module.ProjectAISettingsPage,
  })),
);
const PeoplePage = lazy(() =>
  import("@/pages/PeoplePage").then((module) => ({ default: module.PeoplePage })),
);
const PeopleReviewPage = lazy(() =>
  import("@/pages/PeopleReviewPage").then((module) => ({
    default: module.PeopleReviewPage,
  })),
);
const PhotoQuarantinePage = lazy(() =>
  import("@/pages/PhotoQuarantinePage").then((module) => ({
    default: module.PhotoQuarantinePage,
  })),
);

function RouteLoading() {
  return (
    <div className="min-h-[40vh] flex items-center justify-center text-body-sm text-mute">
      正在加载页面…
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

function AppRoutes() {
  const auth = useAuth();
  const location = useLocation();

  useEffect(() => {
    if (auth.status !== "authenticated" || auth.session?.role !== "admin") return;

    let cancelled = false;

    api.settings
      .getDebug()
      .then((cfg) => {
        if (cancelled) return;
        configureFrontendLogger(cfg.debugMatrix);
        logger.debug("frontend logger configured", {
          frontendLogLevel: cfg.debugMatrix.frontendLogLevel,
        });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        logger.warn("failed to load debug settings for frontend logger", {
          error,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [auth.status, auth.session?.role]);

  if (auth.status === "loading") {
    return (
      <div className="min-h-screen bg-surface-soft flex items-center justify-center text-body-sm text-mute">
        正在检查登录状态
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/m/*" element={<Navigate to="/login" replace />} />
          <Route
            path="*"
            element={<Navigate to="/login" replace state={{ from: location.pathname + location.search }} />}
          />
        </Routes>
      </Suspense>
    );
  }

  return (
    <ProjectProvider>
      <div className="min-h-screen bg-surface-soft">
        <Header />
        <Suspense fallback={<RouteLoading />}>
          <Routes>
            <Route path="/" element={<Navigate to="/photos" replace />} />
            <Route path="/login" element={<Navigate to="/photos" replace />} />
            <Route path="/m" element={<Navigate to="/photos" replace />} />
            <Route path="/m/*" element={<Navigate to="/photos" replace />} />
            <Route path="/photos" element={<PhotosPage />} />
            {/* Legacy route: keep redirect-only behavior with explicit deprecation log. */}
            <Route path="/scan" element={<LegacyScanRouteRedirect />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/people" element={<Navigate to="/photos" replace />} />
            <Route path="/tags" element={<TagsPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route
              path="/settings/*"
              element={auth.session?.role === "admin" ? <SettingsPage /> : <Navigate to="/photos" replace />}
            />
            {/* Project settings center (keeps /settings/ai compatibility inside page) */}
            <Route
              path="/projects/:projectId/settings/*"
              element={
                auth.session?.role === "admin" || auth.session?.role === "project_manager"
                  ? <ProjectAISettingsPage />
                  : <Navigate to="/photos" replace />
              }
            />
            <Route path="/projects/:projectId/people" element={<PeoplePage />} />
            <Route path="/projects/:projectId/people/review" element={<PeopleReviewPage />} />
            <Route path="/projects/:projectId/photo-quarantine" element={<PhotoQuarantinePage />} />
          </Routes>
        </Suspense>
      </div>
    </ProjectProvider>
  );
}
