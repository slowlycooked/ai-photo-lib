import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { PhotosPage } from "@/pages/PhotosPage";
import { SearchPage } from "@/pages/SearchPage";
import { TagsPage } from "@/pages/TagsPage";
import { TasksPage } from "@/pages/TasksPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ProjectAISettingsPage } from "@/pages/ProjectAISettingsPage";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { api } from "@/lib/api";
import { configureFrontendLogger, logger } from "@/lib/logger";

export default function App() {
  useEffect(() => {
    let cancelled = false;

    api.settings
      .getDebug()
      .then((cfg) => {
        if (cancelled) return;
        configureFrontendLogger(cfg);
        logger.debug("frontend logger configured", {
          frontend_log_level: cfg.frontend_log_level,
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
  }, []);

  return (
    <BrowserRouter>
      <ProjectProvider>
        <div className="min-h-screen bg-surface-soft">
          <Header />
          <Routes>
            <Route path="/" element={<Navigate to="/photos" replace />} />
            <Route path="/photos" element={<PhotosPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/tags" element={<TagsPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            {/* Legacy AI settings routes — redirect to tasks tab */}
            <Route path="/project/settings/ai" element={<Navigate to="/tasks?tab=ai-settings" replace />} />
            <Route path="/project/:projectId/settings/ai" element={<ProjectAISettingsPage />} />
            <Route path="/projects/:projectId/settings/ai" element={<ProjectAISettingsPage />} />
          </Routes>
        </div>
      </ProjectProvider>
    </BrowserRouter>
  );
}
