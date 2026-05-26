import { request } from "./client";

export interface AuthSession {
  username: string;
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
