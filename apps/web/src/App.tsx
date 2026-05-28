import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Header } from "@/components/Header";
import { PhotosPage } from "@/pages/PhotosPage";
import { SearchPage } from "@/pages/SearchPage";
import { TagsPage } from "@/pages/TagsPage";
import { TasksPage } from "@/pages/TasksPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ProjectAISettingsPage } from "@/pages/ProjectAISettingsPage";
import { PeoplePage } from "@/pages/PeoplePage";
import { PeopleReviewPage } from "@/pages/PeopleReviewPage";
import { LoginPage } from "@/pages/LoginPage";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { api } from "@/api";
import { configureFrontendLogger, logger } from "@/lib/logger";
import { LegacyScanRouteRedirect } from "@/components/LegacyScanRouteRedirect";

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
    if (auth.status !== "authenticated") return;

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
  }, [auth.status]);

  if (auth.status === "loading") {
    return (
      <div className="min-h-screen bg-surface-soft flex items-center justify-center text-body-sm text-mute">
        正在检查登录状态
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="*"
          element={<Navigate to="/login" replace state={{ from: location.pathname + location.search }} />}
        />
      </Routes>
    );
  }

  return (
    <ProjectProvider>
      <div className="min-h-screen bg-surface-soft">
        <Header />
        <Routes>
          <Route path="/" element={<Navigate to="/photos" replace />} />
          <Route path="/login" element={<Navigate to="/photos" replace />} />
          <Route path="/photos" element={<PhotosPage />} />
          {/* Legacy route: keep redirect-only behavior with explicit deprecation log. */}
          <Route path="/scan" element={<LegacyScanRouteRedirect />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/people" element={<Navigate to="/photos" replace />} />
          <Route path="/tags" element={<TagsPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/settings/*" element={<SettingsPage />} />
          {/* Project settings center (keeps /settings/ai compatibility inside page) */}
          <Route path="/projects/:projectId/settings/*" element={<ProjectAISettingsPage />} />
          <Route path="/projects/:projectId/people" element={<PeoplePage />} />
          <Route path="/projects/:projectId/people/review" element={<PeopleReviewPage />} />
        </Routes>
      </div>
    </ProjectProvider>
  );
}
