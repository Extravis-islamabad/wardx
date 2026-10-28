import { Space, Tooltip, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { Protocol, platformLabel, usesTlsApi } from '@/constants/enums/inventory';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { Target } from '@/services/inventory-services';
import type { useTargets } from '@/features/inventory/hooks';

interface TargetsTableProps {
  query: ReturnType<typeof useTargets>;
  pagination: TablePaginationConfig;
  canManage: boolean;
  onEdit: (target: Target) => void;
  onResetHostKey: (target: Target) => void;
  /** Pin the key the target presents now (no credential sent). */
  onLearnHostKey?: (target: Target) => void;
  onDelete: (target: Target) => void;
}

const CertCell = ({ target }: { target: Target }) => {
  if (!usesTlsApi(target?.platform) || target?.api_tls === false) return null;
  if (target.tls_cert_mismatch_at) {
    return (
      <Tooltip
        title={`API-SSL presented ${target.tls_cert_mismatch_fingerprint ?? 'an unreadable certificate'} instead of the pinned ${target.tls_cert_fingerprint ?? '(none)'}. Rotation and verify are blocked until a certificate is accepted.`}
      >
        <StatusTag label="cert changed" variant={StatusVariant.DANGER} />
      </Tooltip>
    );
  }
  if (target.tls_cert_fingerprint) {
    return (
      <Tooltip title={`API-SSL ${target.tls_cert_fingerprint} — pinned ${target.tls_cert_learned_at ?? ''}`}>
        <StatusTag label="cert pinned" variant={StatusVariant.SUCCESS} />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="Rotation needs the API-SSL certificate pinned (Host key)">
      <StatusTag label="cert not pinned" variant={StatusVariant.OUTLINE} />
    </Tooltip>
  );
};

const SshKeyCell = ({ target }: { target: Target }) => {
  if (target?.host_key_mismatch_at) {
    return (
      <Tooltip
        title={`Presented ${target.host_key_mismatch_fingerprint ?? 'an unreadable key'} instead of the pinned ${target.ssh_host_key_fingerprint ?? '(none)'}. Rotation and verify are blocked until a key is accepted.`}
      >
        <StatusTag label="key changed" variant={StatusVariant.DANGER} />
      </Tooltip>
    );
  }
  if (target?.ssh_host_key_fingerprint) {
    return (
      <Tooltip title={`${target.ssh_host_key_fingerprint} — pinned ${target?.ssh_host_key_learned_at ?? ''}`}>
        <StatusTag label="pinned" variant={StatusVariant.SUCCESS} />
      </Tooltip>
    );
  }
  if (target?.protocol === Protocol.SSH) {
    return (
      <Tooltip title="Pinned on the first gateway session (trust on first use)">
        <StatusTag label="not yet seen" variant={StatusVariant.OUTLINE} />
      </Tooltip>
    );
  }
  return <>—</>;
};

const HostKeyCell = ({ target }: { target: Target }) => (
  <Space size={4} wrap>
    <SshKeyCell target={target} />
    <CertCell target={target} />
  </Space>
);

export function TargetsTable({
  query,
  pagination,
  canManage,
  onEdit,
  onResetHostKey,
  onLearnHostKey,
  onDelete,
}: TargetsTableProps) {
  const columns: TableProps<Target>['columns'] = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Address', key: 'address', render: (_, t) => `${t?.address}:${t?.port}` },
    { title: 'Platform', dataIndex: 'platform', key: 'platform', render: (p: string) => platformLabel(p) },
    {
      title: 'Protocol',
      dataIndex: 'protocol',
      key: 'protocol',
      render: (p: string) => <StatusTag label={p?.toUpperCase() ?? ''} variant={StatusVariant.OUTLINE} />,
    },
    { title: 'Host key', key: 'host_key', render: (_, t) => <HostKeyCell target={t} /> },
    {
      title: 'Rotation',
      key: 'rotation',
      render: (_, t) =>
        t?.non_rotatable_reason ? (
          <StatusTag label={t.non_rotatable_reason} variant={StatusVariant.NEUTRAL} />
        ) : t?.rotation_allowed ? (
          <StatusTag label="allowed" variant={StatusVariant.SUCCESS} />
        ) : (
          <StatusTag label="off" variant={StatusVariant.OUTLINE} />
        ),
    },
    {
      title: 'Tags',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {tags?.map((t) => <StatusTag key={t} label={t} variant={StatusVariant.OUTLINE} />)}
        </Space>
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 260,
      render: (_, t) => (
        <Space>
          <Button variant="admin" size="small" onClick={() => onEdit(t)}>
            Edit
          </Button>
          {onLearnHostKey && t?.protocol === Protocol.SSH && (
            <Tooltip title="Read the key the device presents (no credential sent), compare it, then accept">
              <Button variant="admin" size="small" onClick={() => onLearnHostKey(t)}>
                {t?.host_key_mismatch_at ? 'Review host key' : 'Host key'}
              </Button>
            </Tooltip>
          )}
          {t?.ssh_host_key_fingerprint && (
            <Button variant="admin" size="small" onClick={() => onResetHostKey(t)}>
              Reset host key
            </Button>
          )}
          <Button variant="danger" size="small" onClick={() => onDelete(t)}>
            Delete
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <DataTable<Target>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load targets")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={canManage ? columns : columns?.filter((c) => c?.key !== 'actions')}
    />
  );
}

export default TargetsTable;
