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
import type { LoginResult, Role, User } from '@/types/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  /** Signed in, but the role requires MFA and it is not on yet. */
  needsMfaEnrolment: boolean;
  /** Password accepted; waiting for the authenticator code. */
  awaitingCode: boolean;
  login: (username: string, password: string) => Promise<void>;
  verifyCode: (code: string) => Promise<void>;
  cancelCode: () => void;
  adoptTokens: (access: string, refresh: string) => void;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [signedIn, setSignedIn] = useState(() => !!tokens.access());
  const [mfaToken, setMfaToken] = useState<string | null>(null);

  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => (await authApi.me()).data,
    enabled: signedIn,
    retry: false,
    staleTime: 60_000,
  });
  const mfa = useQuery({
    queryKey: queryKeys.mfa,
    queryFn: async () => (await authApi.mfaStatus()).data,
    enabled: signedIn,
    retry: false,
    staleTime: 60_000,
  });

  const clearSession = useCallback(() => {
    tokens.clear();
    setSignedIn(false);
    setMfaToken(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    const onLogout = () => clearSession();
    const onEnrol = () => void queryClient.invalidateQueries({ queryKey: queryKeys.mfa });
    window.addEventListener('wardx:logout', onLogout);
    window.addEventListener('wardx:mfa-enrol', onEnrol);
    return () => {
      window.removeEventListener('wardx:logout', onLogout);
      window.removeEventListener('wardx:mfa-enrol', onEnrol);
    };
  }, [clearSession, queryClient]);

  const finish = useCallback((result: LoginResult) => {
    if (result.access_token && result.refresh_token) {
      tokens.set({ access_token: result.access_token, refresh_token: result.refresh_token });
      setMfaToken(null);
      setSignedIn(true);
    }
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const { data } = await authApi.login(username, password);
      if (data.mfa_required && data.mfa_token) {
        setMfaToken(data.mfa_token);
        return;
      }
      finish(data);
    },
    [finish],
  );

  const verifyCode = useCallback(
    async (code: string) => {
      if (!mfaToken) throw new Error('Sign in again');
      finish((await authApi.mfaVerify(mfaToken, code)).data);
    },
    [mfaToken, finish],
  );

  const adoptTokens = useCallback(
    (access: string, refresh: string) => {
      tokens.set({ access_token: access, refresh_token: refresh });
      void queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const user = signedIn ? (me.data ?? null) : null;
  const value = useMemo<AuthState>(
    () => ({
      user,
      loading: signedIn && (me.isLoading || mfa.isLoading),
      needsMfaEnrolment: !!mfa.data && mfa.data.required && !mfa.data.enabled,
      awaitingCode: !!mfaToken,
      login,
      verifyCode,
      cancelCode: () => setMfaToken(null),
      adoptTokens,
      logout,
      hasRole: (...roles) => !!user && roles.includes(user.role),
    }),
    [user, signedIn, me.isLoading, mfa.isLoading, mfa.data, mfaToken, login, verifyCode, adoptTokens, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
