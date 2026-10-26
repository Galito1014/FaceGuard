import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { get, post, setUnauthorizedHandler } from "./api";
import type { Me } from "./types";

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (perm: string) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      setMe(await get<Me>("/api/auth/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setMe(null);
      qc.clear();
    });
    refresh();
  }, [refresh, qc]);

  const login = async (username: string, password: string) => {
    const user = await post<Me>("/api/auth/login", { username, password });
    setMe(user);
    return user;
  };

  const logout = async () => {
    try {
      await post("/api/auth/logout");
    } finally {
      setMe(null);
      qc.clear();
    }
  };

  const can = useCallback((perm: string) => !!me?.permissions.includes(perm), [me]);

  return <Ctx.Provider value={{ me, loading, login, logout, refresh, can }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
