/** Wraps /api/v1/auth/*: sign-in, MFA and the signed-in user. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';
import type { AuthSource, Role } from '@/constants/enums/auth';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  locked_until: string | null;
  last_login_at: string | null;
  auth_source: AuthSource;
  disabled_reason: string | null;
  created_at: string;
  /** Direct per-user grants (break-glass); filled in on /auth/me and the users list. */
  direct_permissions?: string[];
  /** MFA state, on the users list. */
  mfa_enabled?: boolean | null;
  /** Effective permission codenames, on /auth/me only. */
  permissions?: string[];
}

export interface LoginResult {
  access_token: string | null;
  refresh_token: string | null;
  token_type: string;
  expires_in: number | null;
  mfa_required: boolean;
  mfa_token: string | null;
  mfa_enrollment_required: boolean;
}

export interface MfaStatus {
  enabled: boolean;
  pending: boolean;
  required: boolean;
  recovery_codes_left: number;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
}

export interface MfaEnableResult {
  recovery_codes: string[];
  tokens: TokenPair | null;
}

export interface RecoveryCodes {
  recovery_codes: string[];
}

const BASE = 'auth';

export const authService = {
  // Sign-in failures render inline on the login card, so they skip the toast.
  async login(username: string, password: string): Promise<ApiResponse<LoginResult>> {
    const { data } = await apiClient.post<ApiResponse<LoginResult>>(
      `${BASE}/login`,
      { username, password },
      { skipErrorNotify: true },
    );
    return data;
  },

  async mfaVerify(mfa_token: string, code: string): Promise<ApiResponse<LoginResult>> {
    const { data } = await apiClient.post<ApiResponse<LoginResult>>(
      `${BASE}/mfa/verify`,
      { mfa_token, code },
      { skipErrorNotify: true },
    );
    return data;
  },

  async me(): Promise<ApiResponse<User>> {
    const { data } = await apiClient.get<ApiResponse<User>>(`${BASE}/me`);
    return data;
  },

  // The session is cleared whatever the server says; a failed logout has nothing to show.
  async logout(): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`${BASE}/logout`, undefined, { skipErrorNotify: true });
    return data;
  },

  async changePassword(current_password: string, new_password: string): Promise<ApiResponse<TokenPair>> {
    const { data } = await apiClient.post<ApiResponse<TokenPair>>(`${BASE}/change-password`, {
      current_password,
      new_password,
    });
    return data;
  },
};

export const mfaService = {
  async status(): Promise<ApiResponse<MfaStatus>> {
    const { data } = await apiClient.get<ApiResponse<MfaStatus>>(`${BASE}/mfa`);
    return data;
  },

  async setup(): Promise<ApiResponse<MfaSetup>> {
    const { data } = await apiClient.post<ApiResponse<MfaSetup>>(`${BASE}/mfa/setup`);
    return data;
  },

  async enable(code: string): Promise<ApiResponse<MfaEnableResult>> {
    const { data } = await apiClient.post<ApiResponse<MfaEnableResult>>(`${BASE}/mfa/enable`, { code });
    return data;
  },

  async regenerateRecoveryCodes(code: string): Promise<ApiResponse<RecoveryCodes>> {
    const { data } = await apiClient.post<ApiResponse<RecoveryCodes>>(`${BASE}/mfa/recovery-codes`, { code });
    return data;
  },

  async disable(code: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`${BASE}/mfa/disable`, { code });
    return data;
  },
};

export default authService;
