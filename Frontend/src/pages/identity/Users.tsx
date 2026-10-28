import { PlusOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, PageShell } from '@/components';
import { usePagination } from '@/hooks';
import { CreateUserModal, UsersTable } from '@/features/identity/components';
import { useResetUserMfa, useUpdateUser, useUsers } from '@/features/identity/hooks';
import type { UserUpdatePayload } from '@/services/identity-services';
import type { User } from '@/services/auth-services';
import { notify } from '@/utils/notify';

export default function Users() {
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const [resettingMfa, setResettingMfa] = useState<User | null>(null);
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
      />
      <CreateUserModal open={creating} onClose={() => setCreating(false)} />
      <ConfirmModal
        open={resettingMfa !== null}
        danger
        title={`Reset MFA for ${resettingMfa?.username ?? ''}?`}
        description="For a lost phone. Their sessions end and they re-enrol at next sign-in."
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
