import { PlusOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, PageShell } from '@/components';
import { usePagination } from '@/hooks';
import { CreateUserModal, UsersTable } from '@/features/identity/components';
import { useResetUserMfa, useSetEmergencyAccess, useUpdateUser, useUsers } from '@/features/identity/hooks';
import { useAuth } from '@/context/AuthContext';
import type { UserUpdatePayload } from '@/services/identity-services';
import type { User } from '@/services/auth-services';
import { notify } from '@/utils/notify';

export default function Users() {
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const [resettingMfa, setResettingMfa] = useState<User | null>(null);
  const [emergency, setEmergency] = useState<{ user: User; grant: boolean } | null>(null);
  const { user: me } = useAuth();
  const { mutateAsync: setEmergencyAccess } = useSetEmergencyAccess();
  const { page, page_size, setPage, paginationFor } = usePagination();
  const users = useUsers({ page, page_size, search: search || undefined });
  const { mutateAsync: updateUser } = useUpdateUser();
  const { mutateAsync: resetMfa } = useResetUserMfa();

  const update = (user: User, payload: UserUpdatePayload) => {
    updateUser({ id: user.id, payload }).catch(() => {
      // apiClient's interceptor already toasted the failure.
    });
  };

  return (
    <PageShell
      title="Users"
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Search"
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          <Button variant="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            Add user
          </Button>
        </>
      }
    >
      <UsersTable
        query={users}
        pagination={paginationFor(users.data?.total)}
        onChangeRole={(u, role) => update(u, { role })}
        onToggleActive={(u, is_active) => update(u, { is_active })}
        onResetMfa={setResettingMfa}
        onEmergency={(user, grant) => setEmergency({ user, grant })}
        selfId={me?.id}
      />
      <ConfirmModal
        open={emergency !== null}
        danger
        title={`${emergency?.grant ? 'Grant' : 'Revoke'} break-glass access ${emergency?.grant ? 'to' : 'from'} ${emergency?.user.username ?? ''}?`}
        description={
          emergency?.grant
            ? 'They can reveal any account in any safe, with a reason. Every use is audited and raises a high-severity alert. This grant raises one too.'
            : 'They lose emergency access. The revoke is audited and raises a high-severity alert.'
        }
        confirmLabel={emergency?.grant ? 'Grant' : 'Revoke'}
        onCancel={() => setEmergency(null)}
        onConfirm={async () => {
          if (!emergency) return;
          try {
            await setEmergencyAccess({ id: emergency.user.id, grant: emergency.grant });
            notify.success(emergency.grant ? 'Break-glass access granted' : 'Break-glass access revoked');
            setEmergency(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
      <CreateUserModal open={creating} onClose={() => setCreating(false)} />
      <ConfirmModal
        open={resettingMfa !== null}
        danger
        title={`Reset MFA for ${resettingMfa?.username ?? ''}?`}
        description={
          resettingMfa?.direct_permissions?.includes('access.emergency')
            ? 'For a lost phone. Their sessions end and they re-enrol at next sign-in. Their break-glass access is revoked (audited, high alert); another administrator must grant it again.'
            : 'For a lost phone. Their sessions end and they re-enrol at next sign-in.'
        }
        confirmLabel="Reset MFA"
        onCancel={() => setResettingMfa(null)}
        onConfirm={async () => {
          if (!resettingMfa) return;
          try {
            await resetMfa(resettingMfa.id);
            notify.success('MFA removed; they set it up again at next sign-in');
            setResettingMfa(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
