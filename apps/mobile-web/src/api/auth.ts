import { request } from "./client";
import type { AuthSession } from "./types";

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
