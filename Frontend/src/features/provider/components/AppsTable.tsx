import { Space, Switch, Tooltip, Typography, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import type { useApps } from '@/features/provider/hooks';
import { tableStateProps } from '@/lib/tableStateProps';
import type { AppIdentity } from '@/services/provider-services';

interface AppsTableProps {
  query: ReturnType<typeof useApps>;
  pagination: TablePaginationConfig;
  onEdit: (app: AppIdentity) => void;
  onOpen: (app: AppIdentity) => void;
  onToggleEnabled: (app: AppIdentity, enabled: boolean) => void;
}

const activeSecrets = (app: AppIdentity) => app.secrets.filter((s) => s.status === 'active').length;

export function AppsTable({ query, pagination, onEdit, onOpen, onToggleEnabled }: AppsTableProps) {
  const columns: TableProps<AppIdentity>['columns'] = [
    {
      title: 'Name',
      key: 'name',
      render: (_, a) => (
        <Space size={4}>
          {a?.name}
          {!a?.usable && (
            <Tooltip title="Disabled, no allowed network, or no active secret: it cannot get a token">
              <span>
                <StatusTag label="not usable" variant={StatusVariant.WARNING} />
              </span>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Client id',
      key: 'client_id',
      render: (_, a) => (
        <Typography.Text code copyable={{ text: a?.client_id }}>
          {a?.client_id}
        </Typography.Text>
      ),
    },
    {
      title: 'Allowed networks',
      key: 'ip_allowlist',
      render: (_, a) =>
        a?.ip_allowlist.length ? (
          <Space size={4} wrap>
            {a.ip_allowlist.map((c) => (
              <StatusTag key={c} label={c} variant={StatusVariant.OUTLINE} />
            ))}
          </Space>
        ) : (
          <StatusTag label="none: no access" variant={StatusVariant.DANGER} />
        ),
    },
    { title: 'Per minute', dataIndex: 'rate_limit_per_minute', key: 'rate' },
    { title: 'Active secrets', key: 'secrets', render: (_, a) => `${activeSecrets(a)} / 2` },
    {
      title: 'Enabled',
      key: 'enabled',
      render: (_, a) => (
        <Switch size="small" aria-label="Enabled" checked={a?.enabled} onChange={(v) => onToggleEnabled(a, v)} />
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 170,
      render: (_, a) => (
        <Space size={4}>
          <Button variant="admin" size="small" onClick={() => onEdit(a)}>
            Edit
          </Button>
          <Button variant="admin" size="small" onClick={() => onOpen(a)}>
            Secrets & fetches
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <DataTable<AppIdentity>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load application identities")}
      dataSource={query.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default AppsTable;
