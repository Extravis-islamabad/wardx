/** Wraps /api/v1/health/cluster (admin: cluster.view). Backend/docs/phase1/HA_DR.md. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';

export interface ClusterLeader {
  node: string;
  term: number;
  elected_at: string;
  last_seen: string;
  fresh: boolean;
}

export interface ClusterReplica {
  application_name: string;
  state: string | null;
  sync_state: string | null;
  replay_lag_seconds: number | null;
  lag_bytes: number | null;
}

/** sync | degraded | async | standalone */
export type SyncState = 'sync' | 'degraded' | 'async' | 'standalone';
/** not_configured | ok | high | unreadable */
export type DrState = 'not_configured' | 'ok' | 'high' | 'unreadable';

export interface ClusterGateway {
  node: string;
  started_at: string;
  last_seen: string;
  host_key_fingerprint: string;
  stopped_at: string | null;
  fresh: boolean;
}

export interface ClusterHealth {
  node: string;
  leader: ClusterLeader | null;
  replication: {
    in_recovery: boolean;
    sync_state: SyncState;
    expect_sync_standby: boolean;
    replicas: ClusterReplica[];
    error: string | null;
  };
  dr: {
    site_configured: boolean;
    replica_name: string | null;
    state: DrState;
    lag_seconds: number | null;
    max_lag_seconds: number;
    reason: string | null;
    rotation_paused: boolean;
  };
  dr_site_configured: boolean;
  gateways: ClusterGateway[];
  gateway_host_keys_consistent: boolean;
}

export const clusterService = {
  async health(): Promise<ApiResponse<ClusterHealth>> {
    const { data } = await apiClient.get<ApiResponse<ClusterHealth>>('health/cluster');
    return data;
  },
};
