/** Wraps /api/v1/sessions/* and /api/v1/gateway/*: recorded gateway sessions. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import {
  RECORDING_VERIFIED_HEADER,
  type CommandVerdict,
  type SessionMode,
  type SessionStatus,
} from '@/constants/enums/sessions';

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
  mode: SessionMode;
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
  verdict: CommandVerdict;
  rule_id: string | null;
}

export interface GatewayInfo {
  host: string;
  port: number;
  login_format: string;
}

export interface SessionRecording {
  text: string;
  verified: boolean;
}

const BASE = 'sessions';

export const gatewayService = {
  async info(): Promise<ApiResponse<GatewayInfo>> {
    const { data } = await apiClient.get<ApiResponse<GatewayInfo>>('gateway/info');
    return data;
  },
};

export const sessionsService = {
  async list(params: PageQuery): Promise<Paginated<GatewaySession>> {
    const { data } = await apiClient.get<Paginated<GatewaySession>>(BASE, { params });
    return data;
  },

  async commands(id: string): Promise<ApiResponse<SessionCommand[]>> {
    const { data } = await apiClient.get<ApiResponse<SessionCommand[]>>(`${BASE}/${id}/commands`);
    return data;
  },

  // The player renders a failed load in place of the recording.
  async recording(id: string): Promise<SessionRecording> {
    const r = await apiClient.get<string>(`${BASE}/${id}/recording`, {
      responseType: 'text',
      skipErrorNotify: true,
    });
    return { text: r.data, verified: r.headers[RECORDING_VERIFIED_HEADER] === 'true' };
  },

  async terminate(id: string): Promise<ApiResponse<GatewaySession>> {
    const { data } = await apiClient.post<ApiResponse<GatewaySession>>(`${BASE}/${id}/terminate`);
    return data;
  },
};

export default sessionsService;
