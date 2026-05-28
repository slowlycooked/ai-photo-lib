import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { logger } from "@/lib/logger";

export function LegacyScanRouteRedirect() {
  const location = useLocation();

  useEffect(() => {
    logger.warn("deprecated frontend route used", {
      legacyPath: location.pathname,
      successorPath: "/tasks?tab=scan",
    });
  }, [location.pathname]);

  return <Navigate to="/tasks?tab=scan" replace />;
}
