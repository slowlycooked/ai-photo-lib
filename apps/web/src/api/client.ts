/**
 * HTTP client utilities shared by all API modules.
 */

export const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    const msg =
      typeof detail === "string"
        ? detail
        : (detail as Record<string, unknown>)?.message
          ? String((detail as Record<string, unknown>).message)
          : JSON.stringify(detail);
    super(msg);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "same-origin",
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.error ?? body?.detail ?? res.statusText;
    if (res.status === 401) {
      window.dispatchEvent(new Event("auth:expired"));
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export function qs(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}
