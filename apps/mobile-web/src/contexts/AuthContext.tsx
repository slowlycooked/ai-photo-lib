import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api, type AuthSession } from "@/api";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  session: AuthSession | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  session: null,
  login: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    let cancelled = false;

    api.auth
      .me()
      .then((nextSession) => {
        if (cancelled) return;
        setSession(nextSession);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        queryClient.clear();
        setSession(null);
        setStatus("anonymous");
      });

    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  useEffect(() => {
    const handleExpired = () => {
      queryClient.clear();
      setSession(null);
      setStatus("anonymous");
    };
    window.addEventListener("auth:expired", handleExpired);
    return () => window.removeEventListener("auth:expired", handleExpired);
  }, [queryClient]);

  const login = useCallback(async (username: string, password: string) => {
    const nextSession = await api.auth.login(username, password);
    queryClient.clear();
    setSession(nextSession);
    setStatus("authenticated");
  }, [queryClient]);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch (error: unknown) {
      if (!(error instanceof ApiError && error.status === 401)) {
        throw error;
      }
    } finally {
      queryClient.clear();
      setSession(null);
      setStatus("anonymous");
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({ status, session, login, logout }),
    [status, session, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
