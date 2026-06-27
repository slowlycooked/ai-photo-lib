import type { AuthSession } from "@/api";

export function canManageProjects(session: AuthSession | null | undefined) {
  return session?.role === "admin" || session?.role === "project_manager";
}
