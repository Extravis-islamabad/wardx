/** Wraps /api/v1/apps/*: application identities (credential provider clients) and their secrets. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export type AppSecretStatus = 'active' | 'expired' | 'revoked';

export interface AppSecret {
  id: string;
  slot: number;
  /** The first characters of the secret, to tell secrets apart; never the secret. */
  prefix: string;
  status: AppSecretStatus;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface AppIdentity {
  id: string;
  name: string;
  description: string | null;
  client_id: string;
  enabled: boolean;
  /** CIDRs; empty = no access. */
  ip_allowlist: string[];
  rate_limit_per_minute: number;
  /** Enabled, at least one allowed network and an active secret. */
  usable: boolean;
  secrets: AppSecret[];
  created_at: string;
  updated_at: string;
}

export interface AppInput {
  name: string;
  description?: string | null;
  enabled?: boolean;
  ip_allowlist: string[];
  rate_limit_per_minute: number;
  secret_expires_at?: string | null;
}

/** Shown once: WardX keeps only a hash of client_secret. */
export interface NewAppSecret {
  app: AppIdentity;
  secret_id: string;
  client_id: string;
  client_secret: string;
}

export interface AppFetchEvent {
  occurred_at: string;
  outcome: 'success' | 'failure';
  source_ip: string | null;
  kind: string | null;
  purpose: string | null;
  account_id: string | null;
  target_id: string | null;
  username: string | null;
  version_id: string | null;
  error_code: string | null;
}

const BASE = 'apps';

export const appsService = {
  async list(params: PageQuery): Promise<Paginated<AppIdentity>> {
    const { data } = await apiClient.get<Paginated<AppIdentity>>(BASE, { params });
    return data;
  },

  async create(payload: AppInput): Promise<ApiResponse<NewAppSecret>> {
    const { data } = await apiClient.post<ApiResponse<NewAppSecret>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: Partial<AppInput>): Promise<ApiResponse<AppIdentity>> {
    const { data } = await apiClient.patch<ApiResponse<AppIdentity>>(`${BASE}/${id}`, payload);
    return data;
  },

  async addSecret(id: string, expiresAt: string | null): Promise<ApiResponse<NewAppSecret>> {
    const { data } = await apiClient.post<ApiResponse<NewAppSecret>>(`${BASE}/${id}/secrets`, {
      expires_at: expiresAt,
    });
    return data;
  },

  async revokeSecret(id: string, secretId: string): Promise<ApiResponse<AppIdentity>> {
    const { data } = await apiClient.post<ApiResponse<AppIdentity>>(`${BASE}/${id}/secrets/${secretId}/revoke`);
    return data;
  },

  async fetches(id: string, params: PageQuery): Promise<Paginated<AppFetchEvent>> {
    const { data } = await apiClient.get<Paginated<AppFetchEvent>>(`${BASE}/${id}/fetches`, { params });
    return data;
  },
};

export default appsService;
