/** Wraps /api/v1/targets/*: the devices and hosts WardX brokers access to. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface HostKeyProbe {
  target_id: string;
  presented_fingerprint: string;
  key_type: string;
  pinned_fingerprint: string | null;
  matches_pin: boolean;
  mismatch_at: string | null;
  mismatch_fingerprint: string | null;
}

/** The API-SSL certificate a target presents now (SHA-256 over DER, AA:BB:...), next to the pin. */
export interface TlsCertProbe {
  target_id: string;
  presented_fingerprint: string;
  subject: string;
  not_after: string | null;
  pinned_fingerprint: string | null;
  matches_pin: boolean;
  mismatch_at: string | null;
  mismatch_fingerprint: string | null;
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
  /** Set when the device presented another key: rotation and verify are blocked until a key is accepted. */
  host_key_mismatch_at?: string | null;
  host_key_mismatch_fingerprint?: string | null;
  /** MikroTik API-SSL port (null = 8729). */
  api_port?: number | null;
  /** False: the device offers only the cleartext API, so it is never rotated. */
  api_tls?: boolean;
  /** Pinned API-SSL certificate (SHA-256 over DER); a mismatch blocks rotation and verify. */
  tls_cert_fingerprint?: string | null;
  tls_cert_learned_at?: string | null;
  tls_cert_mismatch_at?: string | null;
  tls_cert_mismatch_fingerprint?: string | null;
  created_at: string;
  updated_at: string;
  /** Rotation's per-target switch (off by default). */
  rotation_allowed: boolean;
  /** Device-specific password policy caps, e.g. {max_length: 16}. */
  policy_overrides: Record<string, number | string | boolean | string[]>;
  /** Set when the target can never be rotated, e.g. "non-rotatable (Telnet)". */
  non_rotatable_reason: string | null;
}

export type TargetPayload = Partial<Target>;

const BASE = 'targets';

export const targetsService = {
  async list(params: PageQuery): Promise<Paginated<Target>> {
    const { data } = await apiClient.get<Paginated<Target>>(BASE, { params });
    return data;
  },

  async create(payload: TargetPayload): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: TargetPayload): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.patch<ApiResponse<Target>>(`${BASE}/${id}`, payload);
    return data;
  },

  async remove(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}`);
    return data;
  },

  /** Read the key the target presents now, to compare with the device; sends no credential, pins nothing. */
  async probeHostKey(id: string): Promise<ApiResponse<HostKeyProbe>> {
    const { data } = await apiClient.post<ApiResponse<HostKeyProbe>>(`${BASE}/${id}/host-key/probe`);
    return data;
  },

  /** Pin the key, only if the device still presents the fingerprint that was compared. */
  async acceptHostKey(id: string, fingerprint: string): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(`${BASE}/${id}/host-key/accept`, { fingerprint });
    return data;
  },

  async resetHostKey(id: string): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(`${BASE}/${id}/host-key/reset`);
    return data;
  },

  /** Read the API-SSL certificate the target presents now (TLS handshake only; pins nothing). */
  async probeTlsCert(id: string): Promise<ApiResponse<TlsCertProbe>> {
    const { data } = await apiClient.post<ApiResponse<TlsCertProbe>>(`${BASE}/${id}/tls-cert/probe`);
    return data;
  },

  /** Pin the certificate, only if the device still presents the fingerprint that was compared. */
  async acceptTlsCert(id: string, fingerprint: string): Promise<ApiResponse<Target>> {
    const { data } = await apiClient.post<ApiResponse<Target>>(`${BASE}/${id}/tls-cert/accept`, { fingerprint });
    return data;
  },
};

export default targetsService;
