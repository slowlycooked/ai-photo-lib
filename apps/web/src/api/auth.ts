import { request } from "./client";

export interface AuthSession {
  user_id: number | null;
  username: string;
  display_name: string | null;
  role: "admin" | "project_manager" | "viewer";
  capabilities: string[];
  sessionTimeoutMinutes: number;
}

export function login(username: string, password: string): Promise<AuthSession> {
  return request<AuthSession>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

export function me(): Promise<AuthSession> {
  return request<AuthSession>("/auth/me");
}
