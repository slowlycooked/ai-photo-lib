import { useState } from "react";
import { LockKeyhole, LogIn } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "@/api";
import { useAuth } from "@/contexts/AuthContext";

export function LoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (auth.status === "authenticated") {
    return <Navigate to={redirectTo(location.state)} replace />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await auth.login(username.trim(), password);
      navigate(redirectTo(location.state), { replace: true });
    } catch (nextError: unknown) {
      if (nextError instanceof ApiError && nextError.status === 503) {
        setError("登录密码尚未配置，请先在 .env 中设置 AUTH_PASSWORD。");
      } else {
        setError("用户名或密码不正确。");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-surface-soft flex items-center justify-center px-4">
      <section className="w-full max-w-sm bg-canvas border border-hairline rounded-md shadow-sm p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center">
            <LockKeyhole className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-heading-md text-ink">登录</h1>
            <p className="text-body-sm text-mute">AI Photo Library</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="block text-caption-md text-mute mb-1.5">用户名</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              className="w-full rounded-sm border border-hairline bg-surface-card px-3 py-2 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
            />
          </label>
          <label className="block">
            <span className="block text-caption-md text-mute mb-1.5">密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              className="w-full rounded-sm border border-hairline bg-surface-card px-3 py-2 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
            />
          </label>

          {error && <p className="text-body-sm text-primary">{error}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full h-10 rounded-sm bg-primary text-white text-btn-md flex items-center justify-center gap-2 hover:bg-primary-pressed disabled:opacity-60"
          >
            <LogIn className="w-4 h-4" />
            {isSubmitting ? "登录中" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}

function redirectTo(state: unknown): string {
  if (state && typeof state === "object" && "from" in state) {
    const from = (state as { from?: unknown }).from;
    if (typeof from === "string" && from.startsWith("/")) {
      return from;
    }
  }
  return "/photos";
}
