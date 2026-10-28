/** Wraps /api/v1/accounts/*: privileged accounts and their vaulted secrets. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import type { Target } from './targetsServices';

export interface Account {
  id: string;
  target: Pick<Target, 'id' | 'name' | 'address' | 'platform' | 'protocol'>;
  /** Every account belongs to exactly one safe. */
  safe: { id: string; name: string };
  username: string;
  secret_type: string;
  description: string | null;
  has_secret: boolean;
  secret_version: number;
  secret_updated_at: string | null;
  requires_approval: boolean;
  exclusive_checkout: boolean;
  max_checkout_minutes: number;
  active_checkouts: number;
  created_at: string;
}

/** The account as embedded in requests and check-outs. */
export interface AccountBrief {
  id: string;
  username: string;
  target_id: string;
  target_name: string;
  target_address: string;
}

export interface AccountInput {
  target_id: string;
  /** Omitted: the Default safe. Changing it moves the account (manage_accounts on both safes). */
  safe_id?: string;
  username: string;
  secret_type: string;
  description?: string;
  requires_approval: boolean;
  exclusive_checkout: boolean;
  max_checkout_minutes: number;
  secret?: string;
}

const BASE = 'accounts';

export const accountsService = {
  async list(params: PageQuery): Promise<Paginated<Account>> {
    const { data } = await apiClient.get<Paginated<Account>>(BASE, { params });
    return data;
  },

  async create(payload: AccountInput): Promise<ApiResponse<Account>> {
    const { data } = await apiClient.post<ApiResponse<Account>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: Partial<AccountInput>): Promise<ApiResponse<Account>> {
    const { data } = await apiClient.patch<ApiResponse<Account>>(`${BASE}/${id}`, payload);
    return data;
  },

  async setSecret(id: string, value: string): Promise<ApiResponse<Account>> {
    const { data } = await apiClient.put<ApiResponse<Account>>(`${BASE}/${id}/secret`, { value });
    return data;
  },

  async remove(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}`);
    return data;
  },
};

export default accountsService;
