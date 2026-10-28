import axios from 'axios';
import type { ApiResponse } from '@/types/api';
import type { TokenPair } from '@/services/auth-services';
import { AuthEvent } from '@/constants/enums/auth';
import { tokens } from './authStorage';

export const API_BASE_URL = '/api/v1/';

// One refresh at a time: concurrent 401s wait on the same promise.
let refreshing: Promise<string | null> | null = null;

async function refreshOnce(): Promise<string | null> {
  const refresh = tokens.refresh();
  if (!refresh) return null;
  try {
    // Plain axios, not apiClient: a failed refresh must not re-enter the 401 interceptor.
    const { data } = await axios.post<ApiResponse<TokenPair>>(`${API_BASE_URL}auth/refresh`, {
      refresh_token: refresh,
    });
    tokens.set(data.data);
    return data.data.access_token;
  } catch {
    return null;
  }
}

export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= refreshOnce().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

export function clearAuthAndSignOut() {
  tokens.clear();
  window.dispatchEvent(new Event(AuthEvent.LOGOUT));
}
