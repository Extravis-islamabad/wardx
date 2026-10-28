/** Wraps /api/v1/checkouts/*: credential check-outs and audited reveals. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated, UserBrief } from '@/types/api';
import type { CheckoutStatus } from '@/constants/enums/access';
import type { AccountBrief } from '@/services/inventory-services';

export interface Checkout {
  id: string;
  account: AccountBrief;
  user: UserBrief;
  request_id: string | null;
  reason: string;
  status: CheckoutStatus;
  checked_out_at: string;
  expires_at: string;
  checked_in_at: string | null;
  /** A break-glass reveal. */
  emergency?: boolean;
}

export interface RevealedSecret {
  checkout_id: string;
  username: string;
  secret_type: string;
  value: string;
  expires_at: string;
  /** Break-glass only: why the revealed (current) version may not be what the device uses. */
  notice?: string | null;
}

export interface CheckoutCreatePayload {
  account_id: string;
  reason?: string;
  duration_minutes?: number;
  request_id?: string;
}

const BASE = 'checkouts';

export const checkoutsService = {
  async list(params: PageQuery): Promise<Paginated<Checkout>> {
    const { data } = await apiClient.get<Paginated<Checkout>>(BASE, { params });
    return data;
  },

  async create(payload: CheckoutCreatePayload): Promise<ApiResponse<Checkout>> {
    const { data } = await apiClient.post<ApiResponse<Checkout>>(BASE, payload);
    return data;
  },

  // The reveal modal words its own failure in place of the secret.
  async reveal(id: string): Promise<ApiResponse<RevealedSecret>> {
    const { data } = await apiClient.post<ApiResponse<RevealedSecret>>(`${BASE}/${id}/reveal`, undefined, {
      skipErrorNotify: true,
    });
    return data;
  },

  async checkin(id: string): Promise<ApiResponse<Checkout>> {
    const { data } = await apiClient.post<ApiResponse<Checkout>>(`${BASE}/${id}/checkin`);
    return data;
  },
};

export default checkoutsService;
