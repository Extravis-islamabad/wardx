/** Wraps /api/v1/directory/*: LDAP / Active Directory sign-in and scheduled sync. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';
import type { Role } from '@/constants/enums/auth';
import type { SyncStatus } from '@/constants/enums/identity';

export interface RoleMapping {
  group_dn: string;
  role: Role;
}

export interface SyncResult {
  status: SyncStatus;
  dry_run: boolean;
  checked: number;
  disabled: { username: string; reason: string }[];
  enabled: string[];
  role_changes: { username: string; from: string; to: string }[];
  profile_updates: number;
  problems: string[];
  revoked_checkouts: number;
  killed_sessions: number;
}

export interface DirectoryConfig {
  enabled: boolean;
  server_url: string;
  start_tls: boolean;
  verify_tls: boolean;
  ca_cert_pem: string | null;
  bind_dn: string;
  has_bind_password: boolean;
  user_base_dn: string;
  user_filter: string;
  attr_username: string;
  attr_email: string;
  attr_full_name: string;
  group_base_dn: string | null;
  group_filter: string | null;
  role_mappings: RoleMapping[];
  default_role: Role | null;
  /** Active Directory nested groups (in-chain rule); an off-switch for very large directories. */
  nested_groups: boolean;
  timeout_seconds: number;
  sync_interval_minutes: number;
  sync_max_disable_percent: number;
  last_sync_at: string | null;
  last_sync_status: SyncStatus | null;
  last_sync_summary: SyncResult | null;
  /** Outcome of the most recent directory contact (null until WardX has tried). */
  reachable: boolean | null;
  reachability_checked_at: string | null;
  reachability_error: string | null;
  updated_at: string;
}

export type DirectoryConfigInput = Omit<
  DirectoryConfig,
  | 'has_bind_password'
  | 'updated_at'
  | 'last_sync_at'
  | 'last_sync_status'
  | 'last_sync_summary'
  | 'reachable'
  | 'reachability_checked_at'
  | 'reachability_error'
> & {
  bind_password?: string;
};

export interface DirectoryTestResult {
  dn: string;
  username: string;
  email: string | null;
  full_name: string | null;
  groups: string[];
  role: Role | null;
}

const BASE = 'directory';

export const directoryService = {
  async get(): Promise<ApiResponse<DirectoryConfig | null>> {
    const { data } = await apiClient.get<ApiResponse<DirectoryConfig | null>>(BASE);
    return data;
  },

  async save(payload: DirectoryConfigInput): Promise<ApiResponse<DirectoryConfig>> {
    const { data } = await apiClient.put<ApiResponse<DirectoryConfig>>(BASE, payload);
    return data;
  },

  // The lookup card renders a failed test in place of the result.
  async test(username: string): Promise<ApiResponse<DirectoryTestResult>> {
    const { data } = await apiClient.post<ApiResponse<DirectoryTestResult>>(
      `${BASE}/test`,
      { username },
      { skipErrorNotify: true },
    );
    return data;
  },

  async sync(dry_run: boolean, force = false): Promise<ApiResponse<SyncResult>> {
    const { data } = await apiClient.post<ApiResponse<SyncResult>>(`${BASE}/sync`, { dry_run, force });
    return data;
  },
};

export default directoryService;
