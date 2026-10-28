import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { tokens } from '@/lib/authStorage';
import { authKeys } from '@/features/auth/hooks/authKeys';
import { useMe, useSessionMfaStatus } from '@/features/auth/hooks/useAuthSession';
import { authService, type LoginResult, type User } from '@/services/auth-services';
import { AuthEvent, type Role } from '@/constants/enums/auth';
import { ROLE_PERMISSIONS } from '@/constants/enums/permissions';

export type AccessCheck = {
  /** Module code(s). Accepted for the registry's shape; the backend does not license modules yet. */
  module?: string | string[];
  /** Permission codename(s) — any one of them passes. */
  permission?: string | string[];
};

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
  /** The one gate routes, nav and in-page actions read (see `constants/routeAccess.ts`). */
  canAccess: (check: AccessCheck) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

const asList = (v: string | string[] | undefined): string[] => (v === undefined ? [] : Array.isArray(v) ? v : [v]);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [signedIn, setSignedIn] = useState(() => !!tokens.access());
  const [mfaToken, setMfaToken] = useState<string | null>(null);

  const me = useMe(signedIn);
  const mfa = useSessionMfaStatus(signedIn);

  const clearSession = useCallback(() => {
    tokens.clear();
    setSignedIn(false);
    setMfaToken(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    const onLogout = () => clearSession();
    const onEnrol = () => void queryClient.invalidateQueries({ queryKey: authKeys.mfa() });
    window.addEventListener(AuthEvent.LOGOUT, onLogout);
    window.addEventListener(AuthEvent.MFA_ENROL, onEnrol);
    return () => {
      window.removeEventListener(AuthEvent.LOGOUT, onLogout);
      window.removeEventListener(AuthEvent.MFA_ENROL, onEnrol);
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
      const { data } = await authService.login(username, password);
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
      finish((await authService.mfaVerify(mfaToken, code)).data);
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
      await authService.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const user = signedIn ? (me.data ?? null) : null;

  const canAccess = useCallback(
    ({ permission }: AccessCheck) => {
      if (!user) return false;
      const required = asList(permission);
      if (!required.length) return true;
      const held: string[] = ROLE_PERMISSIONS[user.role] ?? [];
      return required.some((p) => held.includes(p));
    },
    [user],
  );

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
      canAccess,
    }),
    [user, signedIn, me.isLoading, mfa.isLoading, mfa.data, mfaToken, login, verifyCode, adoptTokens, logout, canAccess],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
