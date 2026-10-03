import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface AuthContextType {
  token: string | null;
  refreshTokenValue: string | null;
  username: string | null;
  isAuthenticated: boolean;
  setAuth: (token: string, refreshToken: string, username: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("auth_token"));
  const [refreshTokenValue, setRefreshTokenValue] = useState<string | null>(() => localStorage.getItem("auth_refresh_token"));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem("auth_username"));

  const setAuth = useCallback((newToken: string, newRefresh: string, newUsername: string) => {
    localStorage.setItem("auth_token", newToken);
    localStorage.setItem("auth_refresh_token", newRefresh);
    localStorage.setItem("auth_username", newUsername);
    setToken(newToken);
    setRefreshTokenValue(newRefresh);
    setUsername(newUsername);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_refresh_token");
    localStorage.removeItem("auth_username");
    setToken(null);
    setRefreshTokenValue(null);
    setUsername(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, refreshTokenValue, username, isAuthenticated: !!token, setAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
