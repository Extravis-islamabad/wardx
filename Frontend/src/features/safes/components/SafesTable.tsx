import { Space, Typography, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { SafePermission } from '@/constants/enums/safes';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { Safe } from '@/services/safes-services';
import type { useSafes } from '@/features/safes/hooks';
import { SafeHealthTag } from './SafeHealthTag';

interface SafesTableProps {
  query: ReturnType<typeof useSafes>;
  pagination: TablePaginationConfig;
  /** safes.manage: edit any safe, see health, manage any safe's members. */
  canManage: boolean;
  onEdit: (safe: Safe) => void;
  onMembers: (safe: Safe) => void;
}

export function SafesTable({ query, pagination, canManage, onEdit, onMembers }: SafesTableProps) {
  const columns: TableProps<Safe>['columns'] = [
    {
      title: 'Safe',
      key: 'name',
      render: (_, s) => (
        <Space size={4}>
          <Typography.Text strong>{s?.name}</Typography.Text>
          {!s?.is_active && <StatusTag label="inactive" variant={StatusVariant.NEUTRAL} />}
        </Space>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v ?? '—',
    },
    { title: 'Accounts', dataIndex: 'account_count', key: 'account_count', width: 100 },
    { title: 'Members', dataIndex: 'member_count', key: 'member_count', width: 100 },
    {
      title: 'Your permissions',
      key: 'my_permissions',
      render: (_, s) =>
        s?.my_permissions?.length ? (
          <Space size={4} wrap>
            {s.my_permissions.map((p) => (
              <StatusTag key={p} label={p} variant={StatusVariant.OUTLINE} />
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">none</Typography.Text>
        ),
    },
    ...(canManage
      ? [{ title: 'Health', key: 'health', width: 150, render: (_: unknown, s: Safe) => <SafeHealthTag state={s?.health} /> }]
      : []),
    {
      title: '',
      key: 'actions',
      width: 170,
      render: (_, s) => (
        <Space>
          <Button variant="admin" size="small" onClick={() => onMembers(s)}>
            {canManage || s?.my_permissions?.includes(SafePermission.MANAGE_MEMBERS) ? 'Members' : 'Open'}
          </Button>
          {canManage && (
            <Button variant="admin" size="small" onClick={() => onEdit(s)}>
              Edit
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <DataTable<Safe>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load safes")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default SafesTable;
