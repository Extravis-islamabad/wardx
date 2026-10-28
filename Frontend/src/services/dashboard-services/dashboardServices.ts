/** Wraps /api/v1/dashboard/*. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';

export interface DashboardSummary {
  targets: number;
  accounts: number;
  accounts_without_secret: number;
  active_checkouts: number;
  pending_requests: number;
  my_active_checkouts: number;
  my_open_requests: number;
}

export const dashboardService = {
  async summary(): Promise<ApiResponse<DashboardSummary>> {
    const { data } = await apiClient.get<ApiResponse<DashboardSummary>>('dashboard/summary');
    return data;
  },
};

export default dashboardService;
