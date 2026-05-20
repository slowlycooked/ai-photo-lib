import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { PhotosPage } from "@/pages/PhotosPage";
import { SearchPage } from "@/pages/SearchPage";
import { TagsPage } from "@/pages/TagsPage";
import { TasksPage } from "@/pages/TasksPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ProjectAISettingsPage } from "@/pages/ProjectAISettingsPage";
import { ProjectProvider } from "@/contexts/ProjectContext";

export default function App() {
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
