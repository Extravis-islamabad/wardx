/** Wraps /api/v1/alerts/*: security alerts (never deleted; acknowledged once). */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface SecurityAlert {
  id: string;
  created_at: string;
  severity: 'low' | 'medium' | 'high';
  kind: string;
  message: string;
  actor_id: string | null;
  actor_name: string | null;
  object_type: string | null;
  object_id: string | null;
  details: Record<string, unknown>;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

const BASE = 'alerts';

export const alertsService = {
  async list(params: PageQuery): Promise<Paginated<SecurityAlert>> {
    const { data } = await apiClient.get<Paginated<SecurityAlert>>(BASE, { params });
    return data;
  },

  async acknowledge(id: string): Promise<ApiResponse<SecurityAlert>> {
    const { data } = await apiClient.post<ApiResponse<SecurityAlert>>(`${BASE}/${id}/acknowledge`);
    return data;
  },
};

export default alertsService;
