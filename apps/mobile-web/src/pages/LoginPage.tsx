import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: string } | null)?.from ?? "/photos";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await auth.login(username, password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-mobileBg px-5 py-8">
      <section className="mx-auto mt-[12vh] max-w-md rounded-3xl border border-mobileHairline bg-mobileCard p-6">
        <h1 className="text-2xl font-bold text-mobileInk">AI Photo Mobile</h1>
        <p className="mt-2 text-sm text-mobileMute">登录后浏览项目照片并下载原图</p>

        <form className="mt-6 space-y-3" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-1 block text-xs text-mobileMute">用户名</span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="h-11 w-full rounded-xl border border-mobileHairline bg-white px-3 text-sm outline-none ring-mobileAccent focus:ring-2"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-mobileMute">密码</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 w-full rounded-xl border border-mobileHairline bg-white px-3 text-sm outline-none ring-mobileAccent focus:ring-2"
              required
            />
          </label>

          {error && <p className="text-sm text-rose-700">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="h-11 w-full rounded-xl bg-mobileAccent text-sm font-semibold text-white active:bg-mobileAccentPressed disabled:opacity-60"
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
