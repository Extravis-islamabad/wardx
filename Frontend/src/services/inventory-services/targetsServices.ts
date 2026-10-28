/** Wraps /api/v1/targets/*: the devices and hosts WardX brokers access to. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface Target {
  id: string;
  name: string;
  address: string;
  platform: string;
  protocol: string;
  port: number;
  description: string | null;
  tags: string[];
  external_ref: string | null;
  is_active: boolean;
  ssh_host_key_fingerprint: string | null;
  ssh_host_key_learned_at: string | null;
  created_at: string;
  updated_at: string;
  /** Rotation's per-target switch (off by default). */
  rotation_allowed: boolean;
  /** Device-specific password policy caps, e.g. {max_length: 16}. */
  policy_overrides: Record<string, number | string | boolean | string[]>;
  /** Set when the target can never be rotated, e.g. "non-rotatable (Telnet)". */
  non_rotatable_reason: string | null;
}

export type TargetPayload = Partial<Target>;

const BASE = 'targets';

export const targetsService = {
  async list(params: PageQuery): Promise<Paginated<Target>> {
    const { data } = await apiClient.get<Paginated<Target>>(BASE, { params });
    return data;
  },

  async create(payload: TargetPayload): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: TargetPayload): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.patch<ApiResponse<Target>>(`${BASE}/${id}`, payload);
    return data;
  },

  async remove(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}`);
    return data;
  },

  /** Pin the key the target presents now; sends no credential. */
  async learnHostKey(id: string): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(`${BASE}/${id}/host-key/learn`);
    return data;
  },

  async resetHostKey(id: string): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(`${BASE}/${id}/host-key/reset`);
    return data;
  },
};

export default targetsService;
