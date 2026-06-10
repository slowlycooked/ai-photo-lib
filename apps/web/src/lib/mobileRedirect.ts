const DESKTOP_PREFERENCE_KEY = "ai-photo-lib:prefer-desktop-web";

function isMobileUserAgent(): boolean {
  const ua = navigator.userAgent || "";
  return /Android|iPhone|iPad|iPod|IEMobile|Opera Mini|Mobile/i.test(ua);
}

function resolveTargetPath(pathname: string): string {
  if (pathname === "/" || pathname === "") return "/photos";
  if (pathname === "/photos" || pathname.startsWith("/photos/")) return pathname;
  if (pathname === "/search") return pathname;
  if (pathname === "/login") return pathname;
  if (pathname === "/me") return pathname;
  return "/photos";
}

function hasDesktopPreference(): boolean {
  return localStorage.getItem(DESKTOP_PREFERENCE_KEY) === "1";
}

function updatePreferenceFromQuery(params: URLSearchParams): void {
  if (params.get("desktop") === "1") {
    localStorage.setItem(DESKTOP_PREFERENCE_KEY, "1");
    params.delete("desktop");
  }

  if (params.get("mobile") === "1") {
    localStorage.removeItem(DESKTOP_PREFERENCE_KEY);
    params.delete("mobile");
  }
}

export async function maybeRedirectToMobileWeb(): Promise<void> {
  const url = new URL(window.location.href);
  const params = new URLSearchParams(url.search);
  updatePreferenceFromQuery(params);

  const isMobile = isMobileUserAgent();
  const onMobileRoot = url.pathname === "/m" || url.pathname.startsWith("/m/");
  if (!isMobile || onMobileRoot || hasDesktopPreference()) {
    return;
  }

  // Only redirect when a same-origin /m app is actually available.
  // We validate a mobile marker to avoid false positives in dev SPA fallback.
  const probe = await fetch("/m/", { method: "GET" }).catch(() => null);
  if (!probe || !probe.ok) {
    return;
  }
  const html = await probe.text().catch(() => "");
  if (!html.includes('name="ai-photo-lib-app" content="mobile"')) {
    return;
  }

  const targetPath = resolveTargetPath(url.pathname);
  const search = params.toString();
  const suffix = `${targetPath}${search ? `?${search}` : ""}${url.hash}`;
  window.location.replace(`/m${suffix}`);
}
