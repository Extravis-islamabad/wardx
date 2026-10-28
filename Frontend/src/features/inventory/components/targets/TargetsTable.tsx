import { Space, Tooltip, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { Protocol, platformLabel } from '@/constants/enums/inventory';
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
  onDelete: (target: Target) => void;
}

const HostKeyCell = ({ target }: { target: Target }) => {
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

export function TargetsTable({ query, pagination, canManage, onEdit, onResetHostKey, onDelete }: TargetsTableProps) {
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
