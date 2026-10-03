import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { ApiErrorBody, ApiResponse, TokenPair } from '@/types/api';

const ACCESS_KEY = 'wardx.access';
const REFRESH_KEY = 'wardx.refresh';

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const apiClient = axios.create({ baseURL: '/api/v1/' });

apiClient.interceptors.request.use((config) => {
  const access = tokens.access();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

// One refresh at a time: concurrent 401s wait on the same promise.
let refreshing: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  const refresh = tokens.refresh();
  if (!refresh) return null;
  try {
    const { data } = await axios.post<ApiResponse<TokenPair>>('/api/v1/auth/refresh', {
      refresh_token: refresh,
    });
    tokens.set(data.data);
    return data.data.access_token;
  } catch {
    return null;
  }
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as RetriableConfig | undefined;
    const isAuthCall = config?.url?.startsWith('auth/login') || config?.url?.startsWith('auth/refresh');
    if (error.response?.status === 401 && config && !config._retried && !isAuthCall) {
      config._retried = true;
      refreshing ??= refreshAccess().finally(() => {
        refreshing = null;
      });
      const access = await refreshing;
      if (access) {
        config.headers.Authorization = `Bearer ${access}`;
        return apiClient(config);
      }
      tokens.clear();
      window.dispatchEvent(new Event('wardx:logout'));
    }
    return Promise.reject(error);
  },
);

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    if (body?.error) {
      const errors = body.error.details?.errors as { loc: string[]; msg: string }[] | undefined;
      if (errors?.length) {
        return errors.map((e) => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; ');
      }
      return body.error.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong';
}
