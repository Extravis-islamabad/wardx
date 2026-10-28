/** Wraps /api/v1/safes/*: safes, their members and their health. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import type { PrincipalType, SafeHealthState, SafePermission } from '@/constants/enums/safes';

export interface Safe {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  account_count: number;
  member_count: number;
  /** The signed-in user's effective permissions on this safe. */
  my_permissions: SafePermission[];
  /** For safes.manage holders only (null otherwise, and for inactive safes). */
  health: SafeHealthState | null;
  created_at: string;
  updated_at: string;
}

export interface SafeInput {
  name: string;
  description?: string | null;
  is_active?: boolean;
}

export interface SafeMember {
  id: string;
  safe_id: string;
  principal_type: PrincipalType;
  /** user: the user's id; group: the normalised DN; role: the role name. */
  principal_key: string;
  /** For user members: their username. */
  display_name: string | null;
  permissions: SafePermission[];
  created_at: string;
  updated_at: string;
}

export interface SafeMemberInput {
  principal_type: PrincipalType;
  principal_key: string;
  permissions: SafePermission[];
}

export interface SafeHealth {
  safe_id: string;
  name: string;
  state: SafeHealthState;
  severity: 'warning' | 'critical' | null;
  user_members: number;
  role_members: number;
  group_members: number;
}

export interface BreakGlassCoverage {
  eligible_holders: number;
  holders: number;
  minimum: number;
  warning: boolean;
  message: string | null;
}

export interface SafeHealthReport {
  break_glass: BreakGlassCoverage;
  safes: SafeHealth[];
}

const BASE = 'safes';

export const safesService = {
  async list(params: PageQuery): Promise<Paginated<Safe>> {
    const { data } = await apiClient.get<Paginated<Safe>>(BASE, { params });
    return data;
  },

  async create(payload: SafeInput): Promise<ApiResponse<Safe>> {
    const { data } = await apiClient.post<ApiResponse<Safe>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: Partial<SafeInput>): Promise<ApiResponse<Safe>> {
    const { data } = await apiClient.patch<ApiResponse<Safe>>(`${BASE}/${id}`, payload);
    return data;
  },

  async health(): Promise<ApiResponse<SafeHealthReport>> {
    const { data } = await apiClient.get<ApiResponse<SafeHealthReport>>(`${BASE}/health`);
    return data;
  },

  async members(safeId: string): Promise<ApiResponse<SafeMember[]>> {
    const { data } = await apiClient.get<ApiResponse<SafeMember[]>>(`${BASE}/${safeId}/members`);
    return data;
  },

  async addMember(safeId: string, payload: SafeMemberInput): Promise<ApiResponse<SafeMember>> {
    const { data } = await apiClient.post<ApiResponse<SafeMember>>(`${BASE}/${safeId}/members`, payload);
    return data;
  },

  async updateMember(safeId: string, memberId: string, permissions: SafePermission[]): Promise<ApiResponse<SafeMember>> {
    const { data } = await apiClient.patch<ApiResponse<SafeMember>>(`${BASE}/${safeId}/members/${memberId}`, {
      permissions,
    });
    return data;
  },

  async removeMember(safeId: string, memberId: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${safeId}/members/${memberId}`);
    return data;
  },
};

export default safesService;
