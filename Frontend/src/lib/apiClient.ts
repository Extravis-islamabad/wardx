import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { ApiErrorBody } from '@/types/api';
import { ApiErrorCode, AuthEvent, HttpStatus } from '@/constants/enums/auth';
import { notifyApiError } from '@/utils/notifyApiError';
import { tokens } from './authStorage';
import { API_BASE_URL, clearAuthAndSignOut, refreshAccessToken } from './tokenRefresh';

declare module 'axios' {
  interface AxiosRequestConfig {
    /** The caller renders this failure itself, in words — skip the global toast. */
    skipErrorNotify?: boolean;
  }
}

// Per-request flags we tack onto the axios config.
type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

// Auth calls answer 401 for bad credentials; refreshing on them would loop.
const AUTH_CALLS = ['auth/login', 'auth/refresh', 'auth/mfa/verify'];

export const apiClient = axios.create({ baseURL: API_BASE_URL });

apiClient.interceptors.request.use((config) => {
  const access = tokens.access();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const originalRequest = error.config as RetryableConfig | undefined;
    const status = error.response?.status;
    const isAuthCall = AUTH_CALLS.some((u) => originalRequest?.url?.startsWith(u));

    if (status === HttpStatus.UNAUTHORIZED && originalRequest && !originalRequest._retry && !isAuthCall) {
      originalRequest._retry = true;
      const access = await refreshAccessToken();
      if (access) {
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return apiClient(originalRequest);
      }
      clearAuthAndSignOut();
      return Promise.reject(error);
    }

    // The Security page explains enrolment; a toast per refused call would bury it.
    if (error.response?.data?.error?.code === ApiErrorCode.MFA_ENROLLMENT_REQUIRED) {
      window.dispatchEvent(new Event(AuthEvent.MFA_ENROL));
      return Promise.reject(error);
    }

    if (status !== HttpStatus.UNAUTHORIZED && !originalRequest?.skipErrorNotify) {
      try {
        notifyApiError(error);
      } catch {
        // ignore notification errors
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
