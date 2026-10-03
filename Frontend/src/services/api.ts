import { apiClient } from '@/lib/apiClient';
import type {
  AccessRequest,
  Account,
  ApiResponse,
  AuditEvent,
  ChainVerification,
  Checkout,
  CommandRule,
  DashboardSummary,
  GatewayInfo,
  GatewaySession,
  LoginResult,
  MfaStatus,
  PageQuery,
  Paginated,
  RevealedSecret,
  SessionCommand,
  Target,
  TokenPair,
  User,
} from '@/types/api';

const get = async <T>(url: string, params?: PageQuery) => (await apiClient.get<T>(url, { params })).data;
const post = async <T>(url: string, body?: unknown) => (await apiClient.post<T>(url, body)).data;
const patch = async <T>(url: string, body: unknown) => (await apiClient.patch<T>(url, body)).data;
const put = async <T>(url: string, body: unknown) => (await apiClient.put<T>(url, body)).data;
const del = async <T>(url: string) => (await apiClient.delete<T>(url)).data;

export const authApi = {
  login: (username: string, password: string) =>
    post<ApiResponse<LoginResult>>('auth/login', { username, password }),
  mfaVerify: (mfa_token: string, code: string) =>
    post<ApiResponse<LoginResult>>('auth/mfa/verify', { mfa_token, code }),
  mfaStatus: () => get<ApiResponse<MfaStatus>>('auth/mfa'),
  mfaSetup: () => post<ApiResponse<{ secret: string; otpauth_uri: string }>>('auth/mfa/setup'),
  mfaEnable: (code: string) =>
    post<ApiResponse<{ recovery_codes: string[]; tokens: TokenPair | null }>>('auth/mfa/enable', { code }),
  mfaRecoveryCodes: (code: string) =>
    post<ApiResponse<{ recovery_codes: string[] }>>('auth/mfa/recovery-codes', { code }),
  mfaDisable: (code: string) => post<ApiResponse<null>>('auth/mfa/disable', { code }),
  me: () => get<ApiResponse<User>>('auth/me'),
  logout: () => post<ApiResponse<null>>('auth/logout'),
  changePassword: (current_password: string, new_password: string) =>
    post<ApiResponse<TokenPair>>('auth/change-password', { current_password, new_password }),
};

export const dashboardApi = {
  summary: () => get<ApiResponse<DashboardSummary>>('dashboard/summary'),
};

export const targetsApi = {
  list: (q: PageQuery) => get<Paginated<Target>>('targets', q),
  create: (body: Partial<Target>) => post<ApiResponse<Target>>('targets', body),
  update: (id: string, body: Partial<Target>) => patch<ApiResponse<Target>>(`targets/${id}`, body),
  remove: (id: string) => del<ApiResponse<null>>(`targets/${id}`),
  resetHostKey: (id: string) => post<ApiResponse<Target>>(`targets/${id}/host-key/reset`),
};

export interface AccountInput {
  target_id: string;
  username: string;
  secret_type: string;
  description?: string;
  requires_approval: boolean;
  exclusive_checkout: boolean;
  max_checkout_minutes: number;
  secret?: string;
}

export const accountsApi = {
  list: (q: PageQuery) => get<Paginated<Account>>('accounts', q),
  create: (body: AccountInput) => post<ApiResponse<Account>>('accounts', body),
  update: (id: string, body: Partial<AccountInput>) =>
    patch<ApiResponse<Account>>(`accounts/${id}`, body),
  setSecret: (id: string, value: string) =>
    put<ApiResponse<Account>>(`accounts/${id}/secret`, { value }),
  remove: (id: string) => del<ApiResponse<null>>(`accounts/${id}`),
};

export const requestsApi = {
  list: (q: PageQuery) => get<Paginated<AccessRequest>>('requests', q),
  create: (body: { account_id: string; reason: string; ticket_ref?: string; duration_minutes: number }) =>
    post<ApiResponse<AccessRequest>>('requests', body),
  decide: (id: string, approve: boolean, note?: string) =>
    post<ApiResponse<AccessRequest>>(`requests/${id}/decision`, { approve, note }),
  cancel: (id: string) => post<ApiResponse<AccessRequest>>(`requests/${id}/cancel`),
};

export const checkoutsApi = {
  list: (q: PageQuery) => get<Paginated<Checkout>>('checkouts', q),
  create: (body: { account_id: string; reason?: string; duration_minutes?: number; request_id?: string }) =>
    post<ApiResponse<Checkout>>('checkouts', body),
  reveal: (id: string) => post<ApiResponse<RevealedSecret>>(`checkouts/${id}/reveal`),
  checkin: (id: string) => post<ApiResponse<Checkout>>(`checkouts/${id}/checkin`),
};

export const auditApi = {
  list: (q: PageQuery) => get<Paginated<AuditEvent>>('audit/events', q),
  verify: () => post<ApiResponse<ChainVerification>>('audit/verify'),
};

export const usersApi = {
  list: (q: PageQuery) => get<Paginated<User>>('users', q),
  create: (body: { username: string; password: string; email?: string; full_name?: string; role: string }) =>
    post<ApiResponse<User>>('users', body),
  update: (id: string, body: Partial<Pick<User, 'role' | 'is_active' | 'email' | 'full_name'>>) =>
    patch<ApiResponse<User>>(`users/${id}`, body),
  resetPassword: (id: string, new_password: string) =>
    post<ApiResponse<null>>(`users/${id}/reset-password`, { new_password }),
  resetMfa: (id: string) => post<ApiResponse<null>>(`users/${id}/mfa/reset`),
};

export const sessionsApi = {
  gatewayInfo: () => get<ApiResponse<GatewayInfo>>('gateway/info'),
  list: (q: PageQuery) => get<Paginated<GatewaySession>>('sessions', q),
  commands: (id: string) => get<ApiResponse<SessionCommand[]>>(`sessions/${id}/commands`),
  recording: async (id: string) => {
    const r = await apiClient.get<string>(`sessions/${id}/recording`, { responseType: 'text' });
    return { text: r.data, verified: r.headers['x-wardx-recording-verified'] === 'true' };
  },
  terminate: (id: string) => post<ApiResponse<GatewaySession>>(`sessions/${id}/terminate`),
};

export interface RuleInput {
  pattern: string;
  description?: string;
  account_id?: string;
  target_id?: string;
  platform?: string;
}

export const rulesApi = {
  list: () => get<ApiResponse<CommandRule[]>>('command-rules'),
  create: (body: RuleInput) => post<ApiResponse<CommandRule>>('command-rules', body),
  update: (id: string, body: Partial<RuleInput & { is_active: boolean }>) =>
    patch<ApiResponse<CommandRule>>(`command-rules/${id}`, body),
  remove: (id: string) => del<ApiResponse<null>>(`command-rules/${id}`),
  test: (command: string, account_id?: string) =>
    post<ApiResponse<{ blocked: boolean; rule_id: string | null; description: string | null }>>(
      'command-rules/test',
      { command, account_id },
    ),
};
