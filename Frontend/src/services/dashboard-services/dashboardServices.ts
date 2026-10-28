/** Wraps /api/v1/dashboard/*. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';
import type { BreakGlassCoverage, SafeHealth } from '@/services/safes-services';

export interface DashboardSummary {
  targets: number;
  accounts: number;
  accounts_without_secret: number;
  active_checkouts: number;
  pending_requests: number;
  my_active_checkouts: number;
  my_open_requests: number;
}

export interface DirectoryStatus {
  enabled: boolean;
  reachable: boolean | null;
  unreachable: boolean;
  checked_at: string | null;
  error: string | null;
  /** While unreachable: active safes nobody can reach once group memberships count as none. */
  affected_safes: SafeHealth[];
}

/** What needs an administrator's attention (audit.view or safes.manage). */
export interface Attention {
  directory: DirectoryStatus;
  break_glass: BreakGlassCoverage;
  safes_needing_attention: SafeHealth[];
}

export const dashboardService = {
  async attention(): Promise<ApiResponse<Attention>> {
    const { data } = await apiClient.get<ApiResponse<Attention>>('dashboard/attention');
    return data;
  },

  async summary(): Promise<ApiResponse<DashboardSummary>> {
    const { data } = await apiClient.get<ApiResponse<DashboardSummary>>('dashboard/summary');
    return data;
  },
};

export default dashboardService;
