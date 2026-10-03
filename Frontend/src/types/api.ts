export type Role = 'admin' | 'approver' | 'auditor' | 'user';

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string | null;
}

export interface Paginated<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorBody {
  success: false;
  status_code: number;
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  locked_until: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface Target {
  id: string;
  name: string;
  address: string;
  platform: string;
  protocol: string;
  port: number;
  description: string | null;
  tags: string[];
  external_ref: string | null;
  is_active: boolean;
  ssh_host_key_fingerprint: string | null;
  ssh_host_key_learned_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Account {
  id: string;
  target: Pick<Target, 'id' | 'name' | 'address' | 'platform' | 'protocol'>;
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

export interface UserBrief {
  id: string;
  username: string;
  full_name: string | null;
}

export interface AccountBrief {
  id: string;
  username: string;
  target_id: string;
  target_name: string;
  target_address: string;
}

export type RequestStatus = 'pending' | 'approved' | 'denied' | 'cancelled' | 'expired' | 'used';

export interface AccessRequest {
  id: string;
  account: AccountBrief;
  requester: UserBrief;
  reason: string;
  ticket_ref: string | null;
  duration_minutes: number;
  status: RequestStatus;
  decided_by: UserBrief | null;
  decided_at: string | null;
  decision_note: string | null;
  expires_at: string;
  created_at: string;
}

export type CheckoutStatus = 'active' | 'returned' | 'expired' | 'revoked';

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
}

export interface RevealedSecret {
  checkout_id: string;
  username: string;
  secret_type: string;
  value: string;
  expires_at: string;
}

export interface AuditEvent {
  seq: number;
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  object_type: string | null;
  object_id: string | null;
  outcome: string;
  source_ip: string | null;
  details: Record<string, unknown>;
  hash: string;
}

export interface ChainVerification {
  ok: boolean;
  checked: number;
  broken_at_seq: number | null;
  reason: string | null;
}

export interface DashboardSummary {
  targets: number;
  accounts: number;
  accounts_without_secret: number;
  active_checkouts: number;
  pending_requests: number;
  my_active_checkouts: number;
  my_open_requests: number;
}

export interface PageQuery {
  page?: number;
  page_size?: number;
  [key: string]: string | number | boolean | undefined;
}

export type SessionStatus = 'active' | 'closed' | 'terminated' | 'failed';

export interface GatewaySession {
  id: string;
  user_id: string;
  username: string;
  account_id: string | null;
  account_username: string;
  target_id: string | null;
  target_name: string;
  target_address: string;
  protocol: string;
  mode: 'shell' | 'exec';
  exec_command: string | null;
  client_ip: string | null;
  gateway_node: string | null;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  close_reason: string | null;
  terminate_requested_at: string | null;
  has_recording: boolean;
  recording_sha256: string | null;
  recording_bytes: number | null;
  bytes_from_target: number;
  commands_count: number;
  blocked_count: number;
}

export interface SessionCommand {
  id: number;
  occurred_at: string;
  offset_seconds: number;
  command: string;
  verdict: 'allowed' | 'blocked';
  rule_id: string | null;
}

export interface CommandRule {
  id: string;
  pattern: string;
  description: string | null;
  account_id: string | null;
  target_id: string | null;
  platform: string | null;
  is_active: boolean;
  created_at: string;
}

export interface GatewayInfo {
  host: string;
  port: number;
  login_format: string;
}
