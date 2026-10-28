import { Space, Tooltip, Typography, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { Protocol, platformLabel } from '@/constants/enums/inventory';
import { SafePermission } from '@/constants/enums/safes';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { Account } from '@/services/inventory-services';
import { fromNow } from '@/utils/format';
import type { useAccounts } from '@/features/inventory/hooks';

interface AccountsTableProps {
  query: ReturnType<typeof useAccounts>;
  pagination: TablePaginationConfig;
  canManage: boolean;
  onAccess: (account: Account) => void;
  onConnect: (account: Account) => void;
  onSetSecret: (account: Account) => void;
  onEdit: (account: Account) => void;
  onDelete: (account: Account) => void;
  /** The caller's permissions per safe id (from GET /safes); unknown safes stay enabled. */
  safePermissions?: Record<string, string[]>;
}

export function AccountsTable({
  query,
  pagination,
  canManage,
  onAccess,
  onConnect,
  onSetSecret,
  onEdit,
  onDelete,
  safePermissions,
}: AccountsTableProps) {
  const holds = (a: Account, ...perms: SafePermission[]) => {
    const held = safePermissions?.[a?.safe?.id];
    return !held || perms.some((p) => held.includes(p));
  };
  const columns: TableProps<Account>['columns'] = [
    {
      title: 'Account',
      key: 'username',
      render: (_, a) => (
        <Typography.Text strong className="whitespace-nowrap">
          {a?.username}
        </Typography.Text>
      ),
    },
    {
      title: 'Target',
      key: 'target',
      render: (_, a) => (
        <>
          {a?.target?.name} <Typography.Text type="secondary">{a?.target?.address}</Typography.Text>
        </>
      ),
    },
    { title: 'Safe', key: 'safe', render: (_, a) => <StatusTag label={a?.safe?.name ?? '—'} variant={StatusVariant.OUTLINE} /> },
    { title: 'Platform', key: 'platform', render: (_, a) => platformLabel(a?.target?.platform) },
    {
      title: 'Policy',
      key: 'policy',
      render: (_, a) => (
        <Space size={4} wrap>
          {a?.requires_approval && <StatusTag label="approval" variant={StatusVariant.WARNING} />}
          {a?.exclusive_checkout && <StatusTag label="exclusive" variant={StatusVariant.OUTLINE} />}
          <StatusTag label={`${a?.max_checkout_minutes ?? 0} min`} variant={StatusVariant.OUTLINE} />
        </Space>
      ),
    },
    {
      title: 'Secret',
      key: 'secret',
      render: (_, a) =>
        a?.has_secret ? (
          <Tooltip title={`Version ${a?.secret_version}`}>
            <StatusTag label={`stored ${fromNow(a?.secret_updated_at)}`} variant={StatusVariant.SUCCESS} />
          </Tooltip>
        ) : (
          <StatusTag label="none" variant={StatusVariant.WARNING} />
        ),
    },
    {
      title: 'In use',
      dataIndex: 'active_checkouts',
      key: 'active_checkouts',
      render: (n: number) => (n ? <StatusTag label={`${n} active`} variant={StatusVariant.INFO} /> : '—'),
    },
    {
      title: '',
      key: 'actions',
      width: 360,
      render: (_, a) => (
        <Space>
          <Button
            variant="primary"
            size="small"
            disabled={!a?.has_secret || !holds(a, SafePermission.RETRIEVE)}
            onClick={() => onAccess(a)}
          >
            {a?.requires_approval ? 'Request' : 'Check out'}
          </Button>
          {a?.target?.protocol === Protocol.SSH && (
            <Tooltip title="Connect through the session gateway">
              <Button
                variant="admin"
                size="small"
                disabled={!a?.has_secret || !holds(a, SafePermission.USE, SafePermission.RETRIEVE)}
                onClick={() => onConnect(a)}
              >
                Connect
              </Button>
            </Tooltip>
          )}
          {canManage && holds(a, SafePermission.MANAGE_ACCOUNTS) && (
            <>
              <Button variant="admin" size="small" onClick={() => onSetSecret(a)}>
                Set secret
              </Button>
              <Button variant="admin" size="small" onClick={() => onEdit(a)}>
                Edit
              </Button>
              <Button variant="danger" size="small" onClick={() => onDelete(a)}>
                Delete
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <DataTable<Account>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load accounts")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default AccountsTable;
