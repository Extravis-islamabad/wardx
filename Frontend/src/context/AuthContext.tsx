import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { tokens } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import { authApi } from '@/services/api';
import type { Role, User } from '@/types/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [signedIn, setSignedIn] = useState(() => !!tokens.access());

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => (await authApi.me()).data,
    enabled: signedIn,
    retry: false,
    staleTime: 60_000,
  });

  const clearSession = useCallback(() => {
    tokens.clear();
    setSignedIn(false);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    window.addEventListener('wardx:logout', clearSession);
    return () => window.removeEventListener('wardx:logout', clearSession);
  }, [clearSession]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authApi.login(username, password);
    tokens.set(res.data);
    setSignedIn(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const user = signedIn ? (data ?? null) : null;
  const value = useMemo<AuthState>(
    () => ({
      user,
      loading: signedIn && isLoading,
      login,
      logout,
      hasRole: (...roles) => !!user && roles.includes(user.role),
    }),
    [user, signedIn, isLoading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
