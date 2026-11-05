/** Wraps the per-page KPI endpoints (GET /<resource>/stats). Each is counted in the
 * database over exactly the rows the matching list shows the signed-in user. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';

export interface AccountStats {
  total: number;
  in_use: number;
  requires_approval: number;
  exclusive: number;
  without_secret: number;
  out_of_sync: number;
  at_risk: number;
}

export interface TargetStats {
  total: number;
  active: number;
  inactive: number;
  platforms: number;
  host_key_unpinned: number;
  key_changed: number;
}

export interface SafeStats {
  total: number;
  accounts: number;
  memberships: number;
  app_fetch_allowed: number;
  approval_required: number;
  /** For safes.manage holders only; null otherwise. */
  break_glass_only: number | null;
  unreachable: number | null;
}

export interface UserStats {
  total: number;
  active: number;
  disabled: number;
  admins: number;
  approvers: number;
  directory: number;
  mfa_enabled: number;
  admins_without_mfa: number;
  locked: number;
}

export interface AppStats {
  total: number;
  enabled: number;
  disabled: number;
  active_secrets: number;
  secrets_expiring: number;
  enabled_unusable: number;
}

export interface CheckoutStats {
  total: number;
  active: number;
  returned: number;
  expired: number;
  revoked: number;
  mine_active: number;
}

export interface RequestStats {
  total: number;
  pending: number;
  approved: number;
  used: number;
  denied: number;
  expired: number;
  cancelled: number;
  awaiting_me: number;
}

export interface SessionStats {
  total: number;
  active: number;
  closed: number;
  terminated: number;
  failed: number;
  mine: number;
}

export interface RotationStats {
  total: number;
  /** Every job status present, with its count; absent statuses are zero. */
  by_status: Record<string, number>;
}

export interface AuditStats {
  total: number;
  last_24h: number;
  last_7d: number;
  logins_24h: number;
  reveals_24h: number;
  emergency_reveals_7d: number;
  blocked_commands_7d: number;
}

const get = async <T>(path: string): Promise<T> => (await apiClient.get<ApiResponse<T>>(path)).data.data;

export const statsService = {
  accounts: () => get<AccountStats>('accounts/stats'),
  targets: () => get<TargetStats>('targets/stats'),
  safes: () => get<SafeStats>('safes/stats'),
  users: () => get<UserStats>('users/stats'),
  apps: () => get<AppStats>('apps/stats'),
  checkouts: () => get<CheckoutStats>('checkouts/stats'),
  requests: () => get<RequestStats>('requests/stats'),
  sessions: () => get<SessionStats>('sessions/stats'),
  rotationJobs: () => get<RotationStats>('rotation/jobs/stats'),
  audit: () => get<AuditStats>('audit/stats'),
};

export default statsService;
