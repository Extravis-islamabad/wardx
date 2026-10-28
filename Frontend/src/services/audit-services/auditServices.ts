/** Wraps /api/v1/audit/*: the hash-chained audit trail. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface AuditEvent {
  seq: number;
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  object_type: string | null;
  object_id: string | null;
  outcome: string;
  source_ip: string | null;
  details: Record<string, unknown>;
  hash: string;
}

export interface ChainVerification {
  ok: boolean;
  checked: number;
  broken_at_seq: number | null;
  reason: string | null;
}

const BASE = 'audit';

export const auditService = {
  async list(params: PageQuery): Promise<Paginated<AuditEvent>> {
    const { data } = await apiClient.get<Paginated<AuditEvent>>(`${BASE}/events`, { params });
    return data;
  },

  // The page renders the verification failure as a banner.
  async verify(): Promise<ApiResponse<ChainVerification>> {
    const { data } = await apiClient.post<ApiResponse<ChainVerification>>(`${BASE}/verify`, undefined, {
      skipErrorNotify: true,
    });
    return data;
  },
};

export default auditService;
