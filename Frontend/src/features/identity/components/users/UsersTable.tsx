import { Select, Space, Switch, Tooltip, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { AuthSource, type Role } from '@/constants/enums/auth';
import { DisabledReason } from '@/constants/enums/identity';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { StatusVariant } from '@/constants/enums/status';
import { ROLE_SHORT_OPTIONS } from '@/features/identity/constants';
import { tableStateProps } from '@/lib/tableStateProps';
import type { User } from '@/services/auth-services';
import { fmtTime, isFuture } from '@/utils/format';
import type { useUsers } from '@/features/identity/hooks';

interface UsersTableProps {
  query: ReturnType<typeof useUsers>;
  pagination: TablePaginationConfig;
  onChangeRole: (user: User, role: Role) => void;
  onToggleActive: (user: User, isActive: boolean) => void;
  onResetMfa: (user: User) => void;
  /** Grant (true) or revoke (false) break-glass access. */
  onEmergency: (user: User, grant: boolean) => void;
  /** The signed-in user's id: nobody grants break-glass to themselves. */
  selfId?: string;
}

/** Why a user can't be granted break-glass, or null when they can. */
const emergencyBlocker = (u: User, selfId?: string): string | null => {
  if (u.id === selfId) return 'Nobody grants break-glass to themselves';
  if (u.auth_source === AuthSource.LDAP) return 'Directory users cannot hold break-glass (it must work without the directory)';
  if (!u.is_active) return 'The user is disabled';
  if (!u.mfa_enabled) return 'The user must enrol in MFA first';
  return null;
};

export function UsersTable({
  query,
  pagination,
  onChangeRole,
  onToggleActive,
  onResetMfa,
  onEmergency,
  selfId,
}: UsersTableProps) {
  const columns: TableProps<User>['columns'] = [
    {
      title: 'Username',
      key: 'username',
      render: (_, u) => (
        <Space size={4}>
          {u?.username}
          {u?.auth_source === AuthSource.LDAP && <StatusTag label="directory" variant={StatusVariant.PRIMARY} />}
        </Space>
      ),
    },
    { title: 'Name', dataIndex: 'full_name', key: 'full_name', render: (v: string | null) => v ?? '—' },
    {
      title: 'Role',
      key: 'role',
      render: (_, u) => (
        <Select
          size="small"
          className="w-32"
          aria-label="Role"
          value={u?.role}
          options={ROLE_SHORT_OPTIONS}
          onChange={(role) => onChangeRole(u, role)}
        />
      ),
    },
    {
      title: 'Active',
      key: 'is_active',
      render: (_, u) => (
        <Space size={4}>
          <Switch
            size="small"
            aria-label="Active"
            checked={u?.is_active}
            onChange={(isActive) => onToggleActive(u, isActive)}
          />
          {u?.disabled_reason === DisabledReason.DIRECTORY_SYNC && (
            <StatusTag label="left directory" variant={StatusVariant.WARNING} />
          )}
        </Space>
      ),
    },
    {
      title: 'Last login',
      key: 'last_login_at',
      render: (_, u) => (
        <Space size={4}>
          {fmtTime(u?.last_login_at)}
          {u?.locked_until && isFuture(u.locked_until) && <StatusTag label="locked" variant={StatusVariant.DANGER} />}
        </Space>
      ),
    },
    {
      title: 'Break-glass',
      key: 'emergency',
      render: (_, u) => {
        const holds = u?.direct_permissions?.includes(PERMISSIONS.ACCESS_EMERGENCY);
        if (holds)
          return (
            <Space size={4}>
              <StatusTag label="holder" variant={StatusVariant.DANGER} />
              <Button variant="admin" size="small" onClick={() => onEmergency(u, false)}>
                Revoke
              </Button>
            </Space>
          );
        const blocker = emergencyBlocker(u, selfId);
        return (
          <Tooltip title={blocker ?? 'Reveal any account in an emergency (audited and alerted)'}>
            <span>
              <Button variant="admin" size="small" disabled={!!blocker} onClick={() => onEmergency(u, true)}>
                Grant
              </Button>
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: 'MFA',
      key: 'mfa',
      width: 70,
      render: (_, u) => (u?.mfa_enabled ? <StatusTag label="on" variant={StatusVariant.SUCCESS} /> : '—'),
    },
    {
      title: '',
      key: 'actions',
      width: 110,
      render: (_, u) => (
        <Button variant="admin" size="small" onClick={() => onResetMfa(u)}>
          Reset MFA
        </Button>
      ),
    },
  ];

  return (
    <DataTable<User>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load users")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default UsersTable;
