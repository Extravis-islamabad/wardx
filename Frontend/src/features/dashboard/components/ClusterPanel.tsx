import { Alert, Card, Descriptions, Space, Typography } from 'antd';
import { StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { useCluster } from '@/features/dashboard/hooks';
import type { ClusterHealth } from '@/services/dashboard-services';
import { fmtTime } from '@/utils/format';

const SYNC_LABEL: Record<ClusterHealth['replication']['sync_state'], string> = {
  sync: 'Synchronous standby attached',
  degraded: 'Degraded: no synchronous standby (committing asynchronously)',
  async: 'Asynchronous standbys only',
  standalone: 'Single database (no standby)',
};

function DrItem({ dr }: { dr: ClusterHealth['dr'] }) {
  if (!dr.site_configured) {
    return <Typography.Text type="secondary">No DR site configured</Typography.Text>;
  }
  const lag = dr.lag_seconds === null ? 'unknown' : `${Math.round(dr.lag_seconds)} s`;
  return (
    <Space wrap>
      <StatusTag
        label={dr.state === 'ok' ? 'Within limit' : dr.state === 'high' ? 'Lag too high' : 'Lag unreadable'}
        variant={dr.state === 'ok' ? StatusVariant.SUCCESS : StatusVariant.DANGER}
      />
      <Typography.Text>
        {dr.replica_name ?? 'replica not named'}: {lag} (limit {dr.max_lag_seconds} s)
      </Typography.Text>
      {dr.rotation_paused && <Typography.Text type="danger">Scheduled rotations paused</Typography.Text>}
    </Space>
  );
}

/** Cluster health for administrators (HA_DR.md): leader, replication, DR lag, gateway nodes. */
export function ClusterPanel() {
  const cluster = useCluster(true);
  const data = cluster.data;
  if (!data) return null;
  const { leader, replication, dr, gateways, last_restore_drill: drill } = data;
  const degraded = replication.sync_state === 'degraded';
  return (
    <Space orientation="vertical" size={12} className="w-full">
      {degraded && (
        <Alert
          type="error"
          showIcon
          title="Database replication is degraded"
          description="No synchronous standby is attached; a failover now could lose the latest commits."
        />
      )}
      {dr.rotation_paused && (
        <Alert
          type="error"
          showIcon
          title="Scheduled rotations are paused: DR replication lag"
          description={dr.reason ?? 'The DR replica lag could not be read (fail safe).'}
        />
      )}
      {!data.gateway_host_keys_consistent && (
        <Alert
          type="error"
          showIcon
          title="Gateway nodes present different SSH host keys"
          description="Every gateway node must use the same host key file (HA_DR.md §5)."
        />
      )}
      <Card size="small" title="Cluster">
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="Scheduler leader">
            {leader ? (
              <Space wrap>
                <Typography.Text strong>{leader.node}</Typography.Text>
                <StatusTag
                  label={leader.fresh ? 'active' : 'not seen recently'}
                  variant={leader.fresh ? StatusVariant.SUCCESS : StatusVariant.WARNING}
                />
                <Typography.Text type="secondary">since {fmtTime(leader.elected_at)} (term {leader.term})</Typography.Text>
              </Space>
            ) : (
              <Typography.Text type="secondary">No leader recorded yet</Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Replication">
            <Space wrap>
              <StatusTag
                label={SYNC_LABEL[replication.sync_state]}
                variant={degraded ? StatusVariant.DANGER : StatusVariant.OUTLINE}
              />
              {replication.replicas.map((r) => (
                <Typography.Text key={r.application_name} type="secondary">
                  {r.application_name} ({r.sync_state ?? '?'}, {r.state ?? '?'}
                  {r.replay_lag_seconds !== null ? `, ${r.replay_lag_seconds.toFixed(1)} s` : ''})
                </Typography.Text>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="DR site">
            <DrItem dr={dr} />
          </Descriptions.Item>
          <Descriptions.Item label="Restore drill">
            {drill ? (
              <Space wrap>
                <StatusTag
                  label={drill.ok ? 'passed' : 'FAILED'}
                  variant={drill.ok ? StatusVariant.SUCCESS : StatusVariant.DANGER}
                />
                <Typography.Text type="secondary">{fmtTime(drill.ran_at)}</Typography.Text>
              </Space>
            ) : (
              <Typography.Text type="secondary">No restore drill recorded (run one quarterly)</Typography.Text>
            )}
          </Descriptions.Item>
          {gateways.length > 0 && (
            <Descriptions.Item label="Gateway nodes">
              <Space wrap>
                {gateways.map((g) => (
                  <StatusTag
                    key={g.node}
                    label={`${g.node}${g.fresh ? '' : ' (lost)'}`}
                    variant={g.fresh ? StatusVariant.SUCCESS : StatusVariant.DANGER}
                  />
                ))}
              </Space>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>
    </Space>
  );
}

export default ClusterPanel;
