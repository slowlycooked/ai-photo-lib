import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { PhotosPage } from "@/pages/PhotosPage";
import { SearchPage } from "@/pages/SearchPage";
import { TagsPage } from "@/pages/TagsPage";
import { TasksPage } from "@/pages/TasksPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ProjectAISettingsPage } from "@/pages/ProjectAISettingsPage";
import { PeoplePage } from "@/pages/PeoplePage";
import { PeopleReviewPage } from "@/pages/PeopleReviewPage";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { api } from "@/api";
import { configureFrontendLogger, logger } from "@/lib/logger";

export default function App() {
  useEffect(() => {
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
            <Route path="/people" element={<PeoplePage />} />
            <Route path="/tags" element={<TagsPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            {/* Canonical project AI settings route */}
            <Route path="/projects/:projectId/settings/ai" element={<ProjectAISettingsPage />} />
            <Route path="/projects/:projectId/people" element={<PeoplePage />} />
            <Route path="/projects/:projectId/people/review" element={<PeopleReviewPage />} />
          </Routes>
        </div>
      </ProjectProvider>
    </BrowserRouter>
  );
}
