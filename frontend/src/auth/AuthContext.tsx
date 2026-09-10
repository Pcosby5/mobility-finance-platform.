import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  getOne,
  getTokens,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  subscribeToTokens,
} from "@/lib/api";
import type { TokenPair, User } from "@/types/api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  register: (input: {
    username: string;
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const requestSeq = useRef(0);

  // On mount: if a token pair exists, resolve /auth/me/. If it was revoked, the
  // interceptor refreshes once; a null access outcome clears storage and this
  // subscription marks the session unauthenticated.
  useEffect(() => {
    let cancelled = false;

    const unsubscribe = subscribeToTokens((tokens) => {
      if (tokens) return;
      if (!cancelled) {
        requestSeq.current += 1;
        setUser(null);
        setStatus("unauthenticated");
      }
    });

    async function probe() {
      if (!getTokens()) {
        setStatus("unauthenticated");
        return;
      }
      try {
        const me = await getOne<User>("/auth/me/");
        if (!cancelled) {
          setUser(me);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) setStatus("unauthenticated");
      }
    }

    void probe();
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens: TokenPair = await apiLogin(username, password);
    if (!tokens.access) throw new Error("Login response missing access token.");
    const me = await getOne<User>("/auth/me/");
    setUser(me);
    setStatus("authenticated");
  }, []);

  const register = useCallback(
    async (input: {
      username: string;
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
    }) => {
      // Registration deliberately does not log the user in: the new account
      // has no customer profile yet, and login establishes a clean session.
      await apiRegister(input);
    },
    [],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo(
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>.");
  return ctx;
}

/** True for roles that manage customers, inventory, loans and alerts. */
export function canManage(user: User | null): boolean {
  return user?.role === "ADMIN" || user?.role === "OPERATIONS";
}
