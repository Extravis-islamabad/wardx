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
  /** From the safe's approval policy (the per-account flag is retired). */
  requires_approval: boolean;
  exclusive_checkout: boolean;
  max_checkout_minutes: number;
  active_checkouts: number;
  created_at: string;
  // Rotation (Backend/docs/phase1/ROTATION.md); overrides can only make the safe's policy stricter.
  rotation_interval_days: number | null;
  rotate_after_use: boolean;
  password_length: number;
  reconcile_account_id: string | null;
  sync_status: string;
  last_verified_at: string | null;
  last_rotated_at: string | null;
  last_rotation_status: string | null;
  rotation_status: string;
  /** e.g. high_risk_empty_password */
  risk_flags: string[];
}

/** The account as embedded in requests and check-outs. */
export interface AccountBrief {
  id: string;
  username: string;
  target_id: string;
  target_name: string;
  target_address: string;
  safe_id?: string | null;
  safe_name?: string | null;
}

/** SNMPv2c: {version: '2c', community}. SNMPv3: USM fields, those unused by the level left out. */
export type SnmpSecret =
  | { version: '2c'; community: string }
  | {
      version: '3';
      security_name: string;
      security_level: 'noAuthNoPriv' | 'authNoPriv' | 'authPriv';
      auth_protocol?: string;
      auth_password?: string;
      priv_protocol?: string;
      priv_password?: string;
    };

export interface AccountInput {
  target_id: string;
  /** Omitted: the Default safe. Changing it moves the account (manage_accounts on both safes). */
  safe_id?: string;
  username: string;
  secret_type: string;
  description?: string;
  exclusive_checkout: boolean;
  max_checkout_minutes: number;
  secret?: string;
  /** The initial secret of an snmp_v2c / snmp_v3 account (instead of `secret`). */
  snmp?: SnmpSecret;
  rotate_after_use?: boolean;
  rotation_interval_days?: number | null;
  password_length?: number;
  reconcile_account_id?: string | null;
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

  /** A plain value, or the structured secret of an SNMP account. */
  async setSecret(id: string, value: string | SnmpSecret): Promise<ApiResponse<Account>> {
    const body = typeof value === 'string' ? { value } : { snmp: value };
    const { data } = await apiClient.put<ApiResponse<Account>>(`${BASE}/${id}/secret`, body);
    return data;
  },

  async remove(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}`);
    return data;
  },
};

export default accountsService;
