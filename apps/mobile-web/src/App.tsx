import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { BottomNav } from "@/components/BottomNav";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { MobileHomePage } from "@/pages/MobileHomePage";

const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const MobileAccountPage = lazy(() =>
  import("@/pages/MobileAccountPage").then((module) => ({
    default: module.MobileAccountPage,
  })),
);
const MobilePhotoViewerPage = lazy(() =>
  import("@/pages/MobilePhotoViewerPage").then((module) => ({
    default: module.MobilePhotoViewerPage,
  })),
);
const MobileSearchPage = lazy(() =>
  import("@/pages/MobileSearchPage").then((module) => ({
    default: module.MobileSearchPage,
  })),
);

function RouteLoading() {
  return (
    <div className="min-h-[40vh] flex items-center justify-center text-sm text-mobileMute">
      正在加载页面…
    </div>
  );
}

const configuredBasename = import.meta.env.VITE_ROUTER_BASENAME;

function resolveRouterBasename(): string {
  if (configuredBasename) {
    return configuredBasename;
  }
  return window.location.pathname === "/m" || window.location.pathname.startsWith("/m/")
    ? "/m"
    : "/";
}

const routerBasename = resolveRouterBasename();

export default function App() {
  return (
    <BrowserRouter basename={routerBasename}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

function AppRoutes() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "loading") {
    return (
      <div className="min-h-screen bg-mobileBg px-4 py-6 text-sm text-mobileMute">
        正在检查登录状态...
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
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
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route path="/" element={<Navigate to="/photos" replace />} />
          <Route path="/login" element={<Navigate to="/photos" replace />} />
          <Route path="/photos" element={<MobileHomePage />} />
          <Route path="/photos/:photoId" element={<MobilePhotoViewerPage />} />
          <Route path="/search" element={<MobileSearchPage />} />
          <Route path="/me" element={<MobileAccountPage />} />
          <Route path="*" element={<Navigate to="/photos" replace />} />
        </Routes>
      </Suspense>
      <BottomNav />
    </ProjectProvider>
  );
}
