/** Wraps /api/v1/safes/*: safes, their members and their health. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import type {
  ApproverType,
  PrincipalType,
  SafeHealthState,
  SafePermission,
  TicketMode,
} from '@/constants/enums/safes';
import type { AuditEvent } from '@/services/audit-services';

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
  /** Credential provider: apps may fetch from an approval-required safe only when on. */
  allow_app_fetch: boolean;
  /** max_cache_seconds served to apps. */
  app_cache_seconds: number;
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

export interface ApprovalLevel {
  position?: number;
  required_approvals: number;
  approver_type: ApproverType;
  /** user: the user's id; group: the directory group's DN; null for safe approvers. */
  approver_key: string | null;
  /** user levels, in responses: full name, else username. */
  approver_name?: string | null;
}

export interface ApprovalPolicy {
  safe_id?: string;
  approval_required: boolean;
  levels: ApprovalLevel[];
  ticket_mode: TicketMode;
  ticket_pattern: string | null;
  approval_window_minutes: number;
  approval_multi_use: boolean;
  level_timeout_hours: number;
}

export interface SafeAppFetch {
  safe_id?: string;
  approval_required?: boolean;
  allow_app_fetch: boolean;
  app_cache_seconds: number;
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

  async policy(safeId: string): Promise<ApiResponse<ApprovalPolicy>> {
    const { data } = await apiClient.get<ApiResponse<ApprovalPolicy>>(`${BASE}/${safeId}/policy`);
    return data;
  },

  async savePolicy(safeId: string, payload: ApprovalPolicy): Promise<ApiResponse<ApprovalPolicy>> {
    const { data } = await apiClient.put<ApiResponse<ApprovalPolicy>>(`${BASE}/${safeId}/policy`, payload);
    return data;
  },

  /** Events about the safe, its accounts and their requests and check-outs (view_audit). */
  async audit(safeId: string, params: PageQuery): Promise<Paginated<AuditEvent>> {
    const { data } = await apiClient.get<Paginated<AuditEvent>>(`${BASE}/${safeId}/audit`, { params });
    return data;
  },

  async appFetch(safeId: string): Promise<ApiResponse<SafeAppFetch>> {
    const { data } = await apiClient.get<ApiResponse<SafeAppFetch>>(`${BASE}/${safeId}/app-fetch`);
    return data;
  },

  async saveAppFetch(safeId: string, payload: SafeAppFetch): Promise<ApiResponse<SafeAppFetch>> {
    const { data } = await apiClient.put<ApiResponse<SafeAppFetch>>(`${BASE}/${safeId}/app-fetch`, payload);
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
