/** Wraps the break-glass API (access.emergency): account lookup and emergency reveal. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import type { Account } from '@/services/inventory-services';
import type { RevealedSecret } from './checkoutsServices';

export const emergencyService = {
  /** Every account, whatever its safe (no secrets), to pick one in an emergency. */
  async accounts(params: PageQuery): Promise<Paginated<Account>> {
    const { data } = await apiClient.get<Paginated<Account>>('emergency/accounts', { params });
    return data;
  },

  /** Reveals from any safe; audited as secret.emergency_reveal and raises a high alert. */
  async reveal(accountId: string, reason: string): Promise<ApiResponse<RevealedSecret>> {
    const { data } = await apiClient.post<ApiResponse<RevealedSecret>>(`accounts/${accountId}/emergency-reveal`, {
      reason,
    });
    return data;
  },
};

export default emergencyService;
