import { DeleteOutlined, EditOutlined, KeyOutlined, LockOutlined, PlusOutlined, UnlockOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { RevealModal } from '@/components/RevealModal';
import { Role, SECRET_TYPES, platformLabel } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fromNow } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { accountsApi, checkoutsApi, requestsApi, targetsApi } from '@/services/api';
import type { Account, Checkout } from '@/types/api';

// ── Admin: create / edit ──

const accountSchema = z.object({
  target_id: z.string().min(1, 'Choose a target'),
  username: z.string().trim().min(1, 'Required').max(255),
  secret_type: z.string(),
  description: z.string().max(2000).optional(),
  requires_approval: z.boolean(),
  exclusive_checkout: z.boolean(),
  max_checkout_minutes: z.number().int().min(1).max(1440),
  secret: z.string().max(16384).optional(),
});
type AccountValues = z.infer<typeof accountSchema>;

function AccountModal({ account, onClose }: { account: Account | null | undefined; onClose: () => void }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const editing = !!account;
  const targets = useQuery({
    queryKey: queryKeys.targets.list({ page: 1, page_size: 200 }),
    queryFn: () => targetsApi.list({ page: 1, page_size: 200 }),
    enabled: account !== undefined,
  });
  const { control, handleSubmit } = useForm<AccountValues>({
    resolver: zodResolver(accountSchema),
    values: {
      target_id: account?.target.id ?? '',
      username: account?.username ?? '',
      secret_type: account?.secret_type ?? 'password',
      description: account?.description ?? '',
      requires_approval: account?.requires_approval ?? false,
      exclusive_checkout: account?.exclusive_checkout ?? true,
      max_checkout_minutes: account?.max_checkout_minutes ?? 60,
      secret: '',
    },
  });
  const save = useMutation({
    mutationFn: (v: AccountValues) => {
      if (editing) {
        const { description, requires_approval, exclusive_checkout, max_checkout_minutes } = v;
        return accountsApi.update(account.id, { description, requires_approval, exclusive_checkout, max_checkout_minutes });
      }
      return accountsApi.create({ ...v, secret: v.secret || undefined });
    },
    onSuccess: () => {
      message.success(editing ? 'Account updated' : 'Account added');
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
      onClose();
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <Modal
      open={account !== undefined}
      title={editing ? `Edit ${account.username}@${account.target.name}` : 'Add privileged account'}
      onCancel={onClose}
      onOk={handleSubmit((v) => save.mutate(v))}
      confirmLoading={save.isPending}
      okText="Save"
      destroyOnHidden
    >
      <Form layout="vertical">
        <FormField control={control} name="target_id" label="Target" render={(f) => (
          <Select
            disabled={editing}
            showSearch
            optionFilterProp="label"
            loading={targets.isLoading}
            value={(f.value as string) || undefined}
            onChange={f.onChange}
            options={targets.data?.data.map((t) => ({ value: t.id, label: `${t.name} (${t.address})` }))}
          />
        )} />
        <div className="grid grid-cols-2 gap-4">
          <FormField control={control} name="username" label="Username" render={(f) => (
            <Input disabled={editing} value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
          )} />
          <FormField control={control} name="secret_type" label="Secret type" render={(f) => (
            <Select disabled={editing} options={SECRET_TYPES} value={f.value as string} onChange={f.onChange} />
          )} />
        </div>
        {!editing && (
          <FormField control={control} name="secret" label="Current secret" extra="Optional; encrypted in the vault, never shown in lists" render={(f) => (
            <Input.Password autoComplete="new-password" value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
          )} />
        )}
        <div className="grid grid-cols-3 gap-4">
          <FormField control={control} name="requires_approval" label="Needs approval" render={(f) => (
            <Switch checked={f.value as boolean} onChange={f.onChange} />
          )} />
          <FormField control={control} name="exclusive_checkout" label="Exclusive" render={(f) => (
            <Switch checked={f.value as boolean} onChange={f.onChange} />
          )} />
          <FormField control={control} name="max_checkout_minutes" label="Max minutes" render={(f) => (
            <InputNumber className="!w-full" min={1} max={1440} value={f.value as number} onChange={f.onChange} />
          )} />
        </div>
        <FormField control={control} name="description" label="Description" render={(f) => (
          <Input.TextArea rows={2} value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
      </Form>
    </Modal>
  );
}

function SecretModal({ account, onClose }: { account: Account | null; onClose: () => void }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [value, setValue] = useState('');
  const save = useMutation({
    mutationFn: () => accountsApi.setSecret(account!.id, value),
    onSuccess: () => {
      message.success('Secret stored as a new version');
      setValue('');
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
      onClose();
    },
    onError: (e) => message.error(errorMessage(e)),
  });
  return (
    <Modal
      open={!!account}
      title={`Set secret — ${account?.username}@${account?.target.name}`}
      onCancel={() => { setValue(''); onClose(); }}
      onOk={() => save.mutate()}
      okButtonProps={{ disabled: !value }}
      confirmLoading={save.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        Stores the value the account currently has on the target. It does not change the password on the device.
      </Typography.Paragraph>
      <Input.Password autoComplete="new-password" value={value} onChange={(e) => setValue(e.target.value)} />
    </Modal>
  );
}

// ── Users: check out or request ──

const accessSchema = z.object({
  reason: z.string().trim().min(3, 'Give a reason (at least 3 characters)').max(2000),
  ticket_ref: z.string().max(100).optional(),
  duration_minutes: z.number().int().min(1).max(1440),
});
type AccessValues = z.infer<typeof accessSchema>;

function AccessModal({
  account,
  onClose,
  onCheckedOut,
}: {
  account: Account | null;
  onClose: () => void;
  onCheckedOut: (c: Checkout) => void;
}) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const needsApproval = !!account?.requires_approval;
  const { control, handleSubmit, reset } = useForm<AccessValues>({
    resolver: zodResolver(accessSchema),
    values: { reason: '', ticket_ref: '', duration_minutes: Math.min(60, account?.max_checkout_minutes ?? 60) },
  });
  const submit = useMutation({
    mutationFn: async (v: AccessValues) => {
      if (needsApproval) {
        await requestsApi.create({ account_id: account!.id, ...v, ticket_ref: v.ticket_ref || undefined });
        return null;
      }
      return (await checkoutsApi.create({ account_id: account!.id, reason: v.reason, duration_minutes: v.duration_minutes })).data;
    },
    onSuccess: (co) => {
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.requests.all });
      void qc.invalidateQueries({ queryKey: queryKeys.checkouts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
      reset();
      onClose();
      if (co) {
        message.success('Checked out');
        onCheckedOut(co);
      } else {
        message.success('Request sent for approval');
        navigate('/requests');
      }
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <Modal
      open={!!account}
      title={`${needsApproval ? 'Request access to' : 'Check out'} ${account?.username}@${account?.target.name}`}
      onCancel={onClose}
      onOk={handleSubmit((v) => submit.mutate(v))}
      okText={needsApproval ? 'Send request' : 'Check out'}
      confirmLoading={submit.isPending}
      destroyOnHidden
    >
      <Form layout="vertical">
        <FormField control={control} name="reason" label="Reason" render={(f) => (
          <Input.TextArea rows={2} value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <div className="grid grid-cols-2 gap-4">
          {needsApproval && (
            <FormField control={control} name="ticket_ref" label="Ticket / change ref" render={(f) => (
              <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
            )} />
          )}
          <FormField control={control} name="duration_minutes" label={`Minutes (max ${account?.max_checkout_minutes ?? ''})`} render={(f) => (
            <InputNumber className="!w-full" min={1} max={account?.max_checkout_minutes} value={f.value as number} onChange={f.onChange} />
          )} />
        </div>
      </Form>
    </Modal>
  );
}

export default function AccountsPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole(Role.Admin);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Account | null | undefined>(undefined);
  const [settingSecret, setSettingSecret] = useState<Account | null>(null);
  const [accessing, setAccessing] = useState<Account | null>(null);
  const [revealing, setRevealing] = useState<Checkout | null>(null);
  const { page, page_size, setPage, pagination } = usePaging();
  const q = { page, page_size, search: search || undefined };
  const { data, isLoading } = useQuery({ queryKey: queryKeys.accounts.list(q), queryFn: () => accountsApi.list(q) });

  const remove = useMutation({
    mutationFn: (id: string) => accountsApi.remove(id),
    onSuccess: () => {
      message.success('Account deleted');
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Privileged accounts</Typography.Title>
        <Space>
          <Input.Search allowClear placeholder="User, target or address" onSearch={(v) => { setSearch(v); setPage(1); }} />
          {isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing(null)}>Add account</Button>}
        </Space>
      </div>
      <Table<Account>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        columns={[
          { title: 'Account', render: (_, a) => <Typography.Text strong>{a.username}</Typography.Text> },
          { title: 'Target', render: (_, a) => <>{a.target.name} <Typography.Text type="secondary">{a.target.address}</Typography.Text></> },
          { title: 'Platform', render: (_, a) => platformLabel(a.target.platform) },
          {
            title: 'Policy',
            render: (_, a) => (
              <Space size={4} wrap>
                {a.requires_approval && <Tag color="gold">approval</Tag>}
                {a.exclusive_checkout && <Tag>exclusive</Tag>}
                <Tag>{a.max_checkout_minutes} min</Tag>
              </Space>
            ),
          },
          {
            title: 'Secret',
            render: (_, a) =>
              a.has_secret ? (
                <Tooltip title={`Version ${a.secret_version}`}>
                  <Tag icon={<LockOutlined />} color="green">stored {fromNow(a.secret_updated_at)}</Tag>
                </Tooltip>
              ) : (
                <Tag color="orange">none</Tag>
              ),
          },
          { title: 'In use', dataIndex: 'active_checkouts', render: (n: number) => (n ? <Tag color="blue">{n} active</Tag> : '—') },
          {
            title: '',
            width: 220,
            render: (_, a) => (
              <Space>
                <Button
                  size="small"
                  type="primary"
                  icon={<UnlockOutlined />}
                  disabled={!a.has_secret}
                  onClick={() => setAccessing(a)}
                >
                  {a.requires_approval ? 'Request' : 'Check out'}
                </Button>
                {isAdmin && (
                  <>
                    <Tooltip title="Set secret"><Button size="small" icon={<KeyOutlined />} onClick={() => setSettingSecret(a)} /></Tooltip>
                    <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(a)} />
                    <Popconfirm title="Delete account and its stored secrets?" onConfirm={() => remove.mutate(a.id)}>
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </>
                )}
              </Space>
            ),
          },
        ]}
      />
      {editing !== undefined && <AccountModal account={editing} onClose={() => setEditing(undefined)} />}
      <SecretModal account={settingSecret} onClose={() => setSettingSecret(null)} />
      {accessing && <AccessModal account={accessing} onClose={() => setAccessing(null)} onCheckedOut={setRevealing} />}
      <RevealModal checkout={revealing} onClose={() => setRevealing(null)} />
    </>
  );
}
