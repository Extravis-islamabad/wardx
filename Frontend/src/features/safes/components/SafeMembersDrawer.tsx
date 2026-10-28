import { PlusOutlined } from '@ant-design/icons';
import { Alert, Descriptions, Drawer, Select, Space, Tabs, Tooltip, Typography, type TableProps } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, DataTable, StatusTag } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { PrincipalType, SAFE_PERMISSION_OPTIONS, SafePermission } from '@/constants/enums/safes';
import { StatusVariant } from '@/constants/enums/status';
import { useRemoveSafeMember, useSafeMembers, useUpdateSafeMember } from '@/features/safes/hooks';
import { tableStateProps } from '@/lib/tableStateProps';
import type { Safe, SafeMember } from '@/services/safes-services';
import { fmtTime } from '@/utils/format';
import { notify } from '@/utils/notify';
import { useAuth } from '@/context/AuthContext';
import { AddMemberModal } from './AddMemberModal';
import { ApprovalPolicyTab } from './ApprovalPolicyTab';
import { SafeAuditTab } from './SafeAuditTab';
import { SafeAppFetchTab } from './SafeAppFetchTab';
import { SafeHealthTag } from './SafeHealthTag';
import { SafeRotationPolicyTab } from '@/features/rotation/components/SafeRotationPolicyTab';

const DRAWER_SIZE = 900;
const PRINCIPAL_VARIANT: Record<PrincipalType, StatusVariant> = {
  [PrincipalType.USER]: StatusVariant.INFO,
  [PrincipalType.GROUP]: StatusVariant.PRIMARY,
  [PrincipalType.ROLE]: StatusVariant.NEUTRAL,
  [PrincipalType.APP]: StatusVariant.SUCCESS,
};

/** A safe's members, approval policy, audit and details. Role members are read-only. */
export function SafeMembersDrawer({ safe, onClose }: { safe: Safe | null; onClose: () => void }) {
  const { canAccess } = useAuth();
  const canManageSafes = canAccess({ permission: PERMISSIONS.SAFES_MANAGE });
  const canSeeMembers = canManageSafes || !!safe?.my_permissions.includes(SafePermission.MANAGE_MEMBERS);
  const canSeeAudit =
    canAccess({ permission: PERMISSIONS.AUDIT_VIEW }) || !!safe?.my_permissions.includes(SafePermission.VIEW_AUDIT);
  const members = useSafeMembers(canSeeMembers ? safe?.id : undefined);
  const { mutateAsync: updateMember } = useUpdateSafeMember(safe?.id ?? '');
  const { mutateAsync: removeMember } = useRemoveSafeMember(safe?.id ?? '');
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<SafeMember | null>(null);

  const change = (m: SafeMember, permissions: SafePermission[]) => {
    if (!permissions.length) return;
    updateMember({ memberId: m.id, permissions })
      .then(() => notify.success('Permissions updated'))
      .catch(() => {
        // apiClient's interceptor already toasted the failure (self_grant_forbidden included).
      });
  };

  const columns: TableProps<SafeMember>['columns'] = [
    {
      title: 'Member',
      key: 'principal',
      render: (_, m) => (
        <Space size={4}>
          <StatusTag label={m?.principal_type} variant={PRINCIPAL_VARIANT[m?.principal_type]} />
          {m?.principal_type === PrincipalType.GROUP ? (
            <Typography.Text code>{m?.principal_key}</Typography.Text>
          ) : (
            (m?.display_name ?? m?.principal_key)
          )}
        </Space>
      ),
    },
    {
      title: 'Permissions',
      key: 'permissions',
      render: (_, m) =>
        m?.principal_type === PrincipalType.APP ? (
          <Tooltip title="Applications hold only 'fetch' (credential provider)">
            <span>
              <StatusTag label={SafePermission.FETCH} variant={StatusVariant.OUTLINE} />
            </span>
          </Tooltip>
        ) : m?.principal_type === PrincipalType.ROLE ? (
          <Tooltip title="Migrated role member: read-only">
            <Space size={4} wrap>
              {m.permissions.map((p) => (
                <StatusTag key={p} label={p} variant={StatusVariant.OUTLINE} />
              ))}
            </Space>
          </Tooltip>
        ) : (
          <Select
            mode="multiple"
            size="small"
            className="min-w-72"
            aria-label="Permissions"
            value={m?.permissions}
            options={SAFE_PERMISSION_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            onChange={(v) => change(m, v)}
          />
        ),
    },
    {
      title: '',
      key: 'actions',
      width: 100,
      render: (_, m) =>
        m?.principal_type !== PrincipalType.ROLE && (
          <Button variant="danger" size="small" onClick={() => setRemoving(m)}>
            Remove
          </Button>
        ),
    },
  ];

  return (
    <Drawer open={!!safe} onClose={onClose} size={DRAWER_SIZE} title={safe?.name} destroyOnHidden>
      {safe && (
        <Tabs
          defaultActiveKey={canSeeMembers ? 'members' : 'policy'}
          items={[
            ...(canSeeMembers
              ? [
            {
              key: 'members',
              label: 'Members',
              children: (
                <>
                  <Alert
                    className="!mb-3"
                    type="info"
                    showIcon
                    title="Nobody can grant to themselves, a group they belong to, or their own role: another administrator must."
                  />
                  <div className="mb-3 flex justify-end">
                    <Button variant="primary" size="small" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
                      Add member
                    </Button>
                  </div>
                  <DataTable<SafeMember>
                    rowKey="id"
                    {...tableStateProps(members, "Couldn't load members")}
                    dataSource={members.data}
                    pagination={false}
                    columns={columns}
                  />
                </>
              ),
            },
                ]
              : []),
            {
              key: 'policy',
              label: 'Approval policy',
              children: <ApprovalPolicyTab safe={safe} canEdit={canManageSafes} />,
            },
            {
              key: 'rotation',
              label: 'Rotation policy',
              children: <SafeRotationPolicyTab safeId={safe.id} canEdit={canManageSafes} />,
            },
            {
              key: 'app-fetch',
              label: 'Application access',
              children: <SafeAppFetchTab safeId={safe.id} canEdit={canSeeMembers} />,
            },
            ...(canSeeAudit ? [{ key: 'audit', label: 'Audit', children: <SafeAuditTab safeId={safe.id} /> }] : []),
            {
              key: 'details',
              label: 'Details',
              children: (
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Description">{safe.description ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="Status">
                    <StatusTag label={safe.is_active ? 'active' : 'inactive'} />
                  </Descriptions.Item>
                  {safe.health && (
                    <Descriptions.Item label="Health">
                      <SafeHealthTag state={safe.health} />
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="Accounts">{safe.account_count}</Descriptions.Item>
                  <Descriptions.Item label="Your permissions">
                    {safe.my_permissions.join(', ') || 'none'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Created">{fmtTime(safe.created_at)}</Descriptions.Item>
                </Descriptions>
              ),
            },
          ]}
        />
      )}
      <AddMemberModal safe={adding ? safe : null} onClose={() => setAdding(false)} />
      <ConfirmModal
        open={removing !== null}
        danger
        title="Remove this member?"
        description="They lose every permission this membership gave them on the safe."
        confirmLabel="Remove"
        onCancel={() => setRemoving(null)}
        onConfirm={async () => {
          if (!removing) return;
          try {
            await removeMember(removing.id);
            notify.success('Member removed');
            setRemoving(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </Drawer>
  );
}

export default SafeMembersDrawer;
