import { PlusOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Popconfirm, Select, Switch, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { Role } from '@/constants/enums';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { usersApi } from '@/services/api';
import type { User } from '@/types/api';

const ROLE_OPTIONS = [
  { value: Role.User, label: 'User — checks out credentials' },
  { value: Role.Approver, label: 'Approver — decides requests' },
  { value: Role.Auditor, label: 'Auditor — reads the audit trail' },
  { value: Role.Admin, label: 'Administrator' },
];

const strongPassword = z
  .string()
  .min(12, 'At least 12 characters')
  .refine(
    (v) => [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length >= 3,
    'Mix at least three of: lower case, upper case, digits, symbols',
  );

const schema = z.object({
  username: z.string().trim().min(3).max(150).regex(/^[A-Za-z0-9._@-]+$/, 'Letters, digits and . _ @ - only'),
  full_name: z.string().max(255).optional(),
  email: z.union([z.literal(''), z.email()]).optional(),
  role: z.enum(Role),
  password: strongPassword,
});
type Values = z.infer<typeof schema>;

function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { control, handleSubmit, reset } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', full_name: '', email: '', role: Role.User, password: '' },
  });
  const create = useMutation({
    mutationFn: (v: Values) => usersApi.create({ ...v, email: v.email || undefined }),
    onSuccess: () => {
      message.success('User created');
      reset();
      void qc.invalidateQueries({ queryKey: queryKeys.users.all });
      onClose();
    },
    onError: (e) => message.error(errorMessage(e)),
  });
  return (
    <Modal open={open} title="Add user" onCancel={onClose} onOk={handleSubmit((v) => create.mutate(v))} confirmLoading={create.isPending} destroyOnHidden>
      <Form layout="vertical">
        <FormField control={control} name="username" label="Username" render={(f) => (
          <Input autoComplete="off" value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <div className="grid grid-cols-2 gap-4">
          <FormField control={control} name="full_name" label="Full name" render={(f) => (
            <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
          )} />
          <FormField control={control} name="email" label="Email" render={(f) => (
            <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
          )} />
        </div>
        <FormField control={control} name="role" label="Role" render={(f) => (
          <Select options={ROLE_OPTIONS} value={f.value as string} onChange={f.onChange} />
        )} />
        <FormField control={control} name="password" label="Initial password" render={(f) => (
          <Input.Password autoComplete="new-password" value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
      </Form>
    </Modal>
  );
}

export default function UsersPage() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const { page, page_size, setPage, pagination } = usePaging();
  const q = { page, page_size, search: search || undefined };
  const { data, isLoading } = useQuery({ queryKey: queryKeys.users.list(q), queryFn: () => usersApi.list(q) });
  const resetMfa = useMutation({
    mutationFn: (id: string) => usersApi.resetMfa(id),
    onSuccess: () => message.success('MFA removed; they set it up again at next sign-in'),
    onError: (e) => message.error(errorMessage(e)),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<User> }) => usersApi.update(id, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.users.all }),
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Users</Typography.Title>
        <div className="flex gap-2">
          <Input.Search allowClear placeholder="Search" onSearch={(v) => { setSearch(v); setPage(1); }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>Add user</Button>
        </div>
      </div>
      <Table<User>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        columns={[
          {
            title: 'Username',
            render: (_, u) => (
              <>
                {u.username} {u.auth_source === 'ldap' && <Tag color="purple">directory</Tag>}
              </>
            ),
          },
          { title: 'Name', dataIndex: 'full_name', render: (v: string | null) => v ?? '—' },
          {
            title: 'Role',
            render: (_, u) => (
              <Select
                size="small"
                className="w-32"
                value={u.role}
                options={ROLE_OPTIONS.map((o) => ({ value: o.value, label: o.value }))}
                onChange={(role) => update.mutate({ id: u.id, body: { role } })}
              />
            ),
          },
          {
            title: 'Active',
            render: (_, u) => (
              <Switch size="small" checked={u.is_active} onChange={(is_active) => update.mutate({ id: u.id, body: { is_active } })} />
            ),
          },
          {
            title: 'Last login',
            render: (_, u) => (
              <>
                {fmtTime(u.last_login_at)} {u.locked_until && new Date(u.locked_until) > new Date() && <Tag color="red">locked</Tag>}
              </>
            ),
          },
          {
            title: '',
            width: 110,
            render: (_, u) => (
              <Popconfirm
                title={`Reset MFA for ${u.username}?`}
                description="For a lost phone. Their sessions end and they re-enrol at next sign-in."
                onConfirm={() => resetMfa.mutate(u.id)}
              >
                <Button size="small">Reset MFA</Button>
              </Popconfirm>
            ),
          },
        ]}
      />
      {creating && <CreateUserModal open onClose={() => setCreating(false)} />}
    </>
  );
}
