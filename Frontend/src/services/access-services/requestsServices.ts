/** Wraps /api/v1/requests/*: approval requests for accounts that need one. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated, UserBrief } from '@/types/api';
import type { RequestStatus } from '@/constants/enums/access';
import type { AccountBrief } from '@/services/inventory-services';

export interface AccessRequest {
  id: string;
  account: AccountBrief;
  requester: UserBrief;
  reason: string;
  ticket_ref: string | null;
  duration_minutes: number;
  status: RequestStatus;
  decided_by: UserBrief | null;
  decided_at: string | null;
  decision_note: string | null;
  /** Pending: the current level's deadline. Approved: the end of the window (valid_until). */
  expires_at: string;
  created_at: string;
  current_level: number;
  level_count: number;
  levels: RequestLevel[];
  decisions: RequestDecision[];
  approved_at: string | null;
  valid_until: string | null;
  multi_use: boolean;
  uses: number;
}

export interface RequestLevel {
  position: number;
  required_approvals: number;
  approver_type: 'safe_approvers' | 'user' | 'group';
  /** user levels: the user's id (for linking); group levels: the DN. */
  approver_key: string | null;
  /** user levels: full name, else username. */
  approver_name?: string | null;
  state: 'approved' | 'denied' | 'current' | 'waiting';
  approvals: number;
}

export interface RequestDecision {
  level: number;
  approver: UserBrief;
  approve: boolean;
  note: string | null;
  decided_at: string;
}

export interface RequestCreatePayload {
  account_id: string;
  reason: string;
  ticket_ref?: string;
  duration_minutes: number;
}

export interface RequestDecisionPayload {
  approve: boolean;
  note?: string;
}

const BASE = 'requests';

export const requestsService = {
  async list(params: PageQuery): Promise<Paginated<AccessRequest>> {
    const { data } = await apiClient.get<Paginated<AccessRequest>>(BASE, { params });
    return data;
  },

  async create(payload: RequestCreatePayload): Promise<ApiResponse<AccessRequest>> {
    const { data } = await apiClient.post<ApiResponse<AccessRequest>>(BASE, payload);
    return data;
  },

  async decide(id: string, payload: RequestDecisionPayload): Promise<ApiResponse<AccessRequest>> {
    const { data } = await apiClient.post<ApiResponse<AccessRequest>>(`${BASE}/${id}/decision`, payload);
    return data;
  },

  async cancel(id: string): Promise<ApiResponse<AccessRequest>> {
    const { data } = await apiClient.post<ApiResponse<AccessRequest>>(`${BASE}/${id}/cancel`);
    return data;
  },
};

export default requestsService;
