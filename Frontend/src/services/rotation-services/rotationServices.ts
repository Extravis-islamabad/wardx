/** Wraps the rotation API: account rotation, jobs, review, safe rotation policy. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface RotationStep {
  step: string;
  outcome: string;
  secret_version: number | null;
  detail: string | null;
  /** Device conversation with every secret replaced by ****. */
  transcript: string | null;
  started_at: string;
  finished_at: string;
  /** The device channel the step used (api-ssl, ssh), when it used one. */
  channel?: string | null;
}

export interface RotationJob {
  id: string;
  /** On-demand rotate / reconcile queued while the DR replica lags (HA_DR.md §6.1). */
  dr_lag_warning?: string | null;
  account_id: string;
  account_username: string;
  target_id: string;
  target_name: string;
  safe_id: string;
  reason: string;
  status: string;
  requested_by: string | null;
  note: string | null;
  dry_run: boolean;
  not_before: string;
  attempts: number;
  waiting_since: string | null;
  release_alerted_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  from_version: number | null;
  candidate_version: number | null;
  secret_versions_touched: number[];
  driver: string | null;
  detail: string | null;
  verify_result: string | null;
  resolution: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
  steps: RotationStep[];
}

export interface MaintenanceWindow {
  days: number[];
  start_hour: number;
  end_hour: number;
}

export interface SafeRotationPolicy {
  safe_id?: string;
  rotate_after_use: boolean;
  rotation_interval_days: number | null;
  verify_interval_hours: number;
  auto_reconcile: boolean;
  maintenance_window: MaintenanceWindow | null;
  max_release_wait_minutes: number;
}

export interface AccountRotation {
  account_id: string;
  username: string;
  target_name: string;
  platform: string;
  protocol: string;
  sync_status: string;
  rotation_status: string;
  last_rotated_at: string | null;
  last_rotation_status: string | null;
  last_verified_at: string | null;
  last_verify_method: string | null;
  risk_flags: string[];
  risk_accepted_by: string | null;
  risk_accepted_at: string | null;
  risk_accepted_reason: string | null;
  reconcile_account_id: string | null;
  rotation_allowed: boolean;
  rotation_enabled: boolean;
  host_key_pinned: boolean;
  non_rotatable_reason: string | null;
  /** Why the target's pinned identities block rotation now (missing pin, changed key or certificate). */
  identity_blocker?: string | null;
  effective_policy: Record<string, unknown> | null;
  policy_error: string | null;
  effective_interval_days: number | null;
  effective_rotate_after_use: boolean;
  safe_policy: SafeRotationPolicy;
  open_job: RotationJob | null;
  jobs: RotationJob[];
  /** Set while the DR replica lags or its lag is unreadable (HA_DR.md §6.1); null without a DR site. */
  dr_lag_warning: string | null;
}

export interface RotationAccountBrief {
  id: string;
  username: string;
  safe_id: string;
  sync_status: string;
  risk_flags: string[];
  last_verified_at: string | null;
  risk_accepted_by: string | null;
  risk_accepted_by_name: string | null;
  risk_accepted_at: string | null;
  risk_accepted_reason: string | null;
}

export interface RotationAttention {
  needs_attention: RotationJob[];
  out_of_sync: RotationAccountBrief[];
  verify_untrustworthy: RotationAccountBrief[];
  confirmed_untrustworthy: RotationAccountBrief[];
  empty_password: RotationAccountBrief[];
  release_overdue: RotationJob[];
}

export type RotationOperation = 'rotate' | 'verify' | 'reconcile';
export type Resolution = 'keep_current' | 'use_candidate' | 'set_secret' | 'reconcile';

export const rotationService = {
  async account(accountId: string): Promise<ApiResponse<AccountRotation>> {
    const { data } = await apiClient.get<ApiResponse<AccountRotation>>(`accounts/${accountId}/rotation`);
    return data;
  },

  async request(
    accountId: string,
    op: RotationOperation,
    body: { reason: string; dry_run?: boolean },
  ): Promise<ApiResponse<RotationJob>> {
    const { data } = await apiClient.post<ApiResponse<RotationJob>>(`accounts/${accountId}/${op}`, body);
    return data;
  },

  async confirm(accountId: string, reason: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`accounts/${accountId}/rotation/confirm`, { reason });
    return data;
  },

  async jobs(params: PageQuery): Promise<Paginated<RotationJob>> {
    const { data } = await apiClient.get<Paginated<RotationJob>>('rotation/jobs', { params });
    return data;
  },

  async job(jobId: string): Promise<ApiResponse<RotationJob>> {
    const { data } = await apiClient.get<ApiResponse<RotationJob>>(`rotation/jobs/${jobId}`);
    return data;
  },

  async resolve(
    jobId: string,
    body: { action: Resolution; note: string; secret?: string },
  ): Promise<ApiResponse<RotationJob>> {
    const { data } = await apiClient.post<ApiResponse<RotationJob>>(`rotation/jobs/${jobId}/resolve`, body);
    return data;
  },

  async attention(): Promise<ApiResponse<RotationAttention>> {
    const { data } = await apiClient.get<ApiResponse<RotationAttention>>('rotation/attention');
    return data;
  },

  async safePolicy(safeId: string): Promise<ApiResponse<SafeRotationPolicy>> {
    const { data } = await apiClient.get<ApiResponse<SafeRotationPolicy>>(`safes/${safeId}/rotation-policy`);
    return data;
  },

  async saveSafePolicy(safeId: string, body: SafeRotationPolicy): Promise<ApiResponse<SafeRotationPolicy>> {
    const { data } = await apiClient.put<ApiResponse<SafeRotationPolicy>>(`safes/${safeId}/rotation-policy`, body);
    return data;
  },
};

export default rotationService;
