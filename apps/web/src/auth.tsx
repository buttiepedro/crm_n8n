import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

export type Me = {
  id: string;
  email: string;
  name: string;
  role: string;
  permissions: string[];
  configPanelUntil: string | null;
};

type AuthState = {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  can: (perm: string) => boolean;
};

const AuthContext = createContext<AuthState>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.post("/auth/logout");
    setMe(null);
  }, []);

  const can = useCallback((perm: string) => me?.permissions.includes(perm) ?? false, [me]);

  return (
    <AuthContext.Provider value={{ me, loading, refresh, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
