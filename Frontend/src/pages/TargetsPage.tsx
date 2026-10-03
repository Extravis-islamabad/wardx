import { DeleteOutlined, EditOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography } from 'antd';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { PLATFORMS, PROTOCOLS, Role, platformLabel } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import { targetsApi } from '@/services/api';
import type { Target } from '@/types/api';

const schema = z.object({
  name: z.string().trim().min(1, 'Required').max(255),
  address: z.string().trim().min(1, 'Required').max(255),
  platform: z.string().min(1, 'Required'),
  protocol: z.enum(PROTOCOLS),
  port: z.number().int().min(1).max(65535).nullable(),
  description: z.string().max(2000).optional(),
  tags: z.array(z.string()),
});
type Values = z.infer<typeof schema>;

function TargetModal({ target, onClose }: { target: Target | null | undefined; onClose: () => void }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const editing = !!target;
  const { control, handleSubmit } = useForm<Values>({
    resolver: zodResolver(schema),
    values: {
      name: target?.name ?? '',
      address: target?.address ?? '',
      platform: target?.platform ?? 'cisco_ios',
      protocol: (target?.protocol as Values['protocol']) ?? 'ssh',
      port: target?.port ?? null,
      description: target?.description ?? '',
      tags: target?.tags ?? [],
    },
  });
  const save = useMutation({
    mutationFn: (v: Values) => {
      const body = { ...v, port: v.port ?? undefined };
      return editing ? targetsApi.update(target.id, body) : targetsApi.create(body);
    },
    onSuccess: () => {
      message.success(editing ? 'Target updated' : 'Target added');
      void qc.invalidateQueries({ queryKey: queryKeys.targets.all });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
      onClose();
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <Modal
      open={target !== undefined}
      title={editing ? `Edit ${target.name}` : 'Add target'}
      onCancel={onClose}
      onOk={handleSubmit((v) => save.mutate(v))}
      confirmLoading={save.isPending}
      okText="Save"
      destroyOnHidden
    >
      <Form layout="vertical">
        <FormField control={control} name="name" label="Name" render={(f) => (
          <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <FormField control={control} name="address" label="Address (IP or hostname)" render={(f) => (
          <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <FormField control={control} name="platform" label="Platform" render={(f) => (
          <Select options={PLATFORMS} value={f.value as string} onChange={f.onChange} showSearch optionFilterProp="label" />
        )} />
        <div className="grid grid-cols-2 gap-4">
          <FormField control={control} name="protocol" label="Protocol" render={(f) => (
            <Select options={PROTOCOLS.map((p) => ({ value: p, label: p.toUpperCase() }))} value={f.value as string} onChange={f.onChange} />
          )} />
          <FormField control={control} name="port" label="Port" extra="Blank = protocol default" render={(f) => (
            <InputNumber className="!w-full" min={1} max={65535} value={f.value as number | null} onChange={f.onChange} />
          )} />
        </div>
        <FormField control={control} name="tags" label="Tags" render={(f) => (
          <Select mode="tags" value={f.value as string[]} onChange={f.onChange} tokenSeparators={[',']} />
        )} />
        <FormField control={control} name="description" label="Description" render={(f) => (
          <Input.TextArea rows={2} value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
      </Form>
    </Modal>
  );
}

export default function TargetsPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole(Role.Admin);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Target | null | undefined>(undefined);
  const { page, page_size, setPage, pagination } = usePaging();
  const q = { page, page_size, search: search || undefined };
  const { data, isLoading } = useQuery({ queryKey: queryKeys.targets.list(q), queryFn: () => targetsApi.list(q) });

  const remove = useMutation({
    mutationFn: (id: string) => targetsApi.remove(id),
    onSuccess: () => {
      message.success('Target deleted');
      void qc.invalidateQueries({ queryKey: queryKeys.targets.all });
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  const resetKey = useMutation({
    mutationFn: (id: string) => targetsApi.resetHostKey(id),
    onSuccess: () => {
      message.success('Host key cleared; the next session pins the key the device presents');
      void qc.invalidateQueries({ queryKey: queryKeys.targets.all });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Targets</Typography.Title>
        <Space>
          <Input.Search allowClear placeholder="Name or address" onSearch={(v) => { setSearch(v); setPage(1); }} />
          {isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing(null)}>Add target</Button>}
        </Space>
      </div>
      <Table<Target>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        columns={[
          { title: 'Name', dataIndex: 'name' },
          { title: 'Address', render: (_, t) => `${t.address}:${t.port}` },
          { title: 'Platform', dataIndex: 'platform', render: platformLabel },
          { title: 'Protocol', dataIndex: 'protocol', render: (p: string) => <Tag>{p.toUpperCase()}</Tag> },
          {
            title: 'Host key',
            render: (_, t) =>
              t.ssh_host_key_fingerprint ? (
                <Tooltip title={`${t.ssh_host_key_fingerprint} — pinned ${t.ssh_host_key_learned_at ?? ''}`}>
                  <Tag icon={<KeyOutlined />} color="green">pinned</Tag>
                </Tooltip>
              ) : t.protocol === 'ssh' ? (
                <Tooltip title="Pinned on the first gateway session (trust on first use)">
                  <Tag>not yet seen</Tag>
                </Tooltip>
              ) : (
                '—'
              ),
          },
          { title: 'Tags', dataIndex: 'tags', render: (tags: string[]) => tags.map((t) => <Tag key={t}>{t}</Tag>) },
          ...(isAdmin
            ? [{
                title: '',
                width: 140,
                render: (_: unknown, t: Target) => (
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(t)} />
                    {t.ssh_host_key_fingerprint && (
                      <Popconfirm
                        title="Reset the pinned host key?"
                        description="Only after confirming the device's key really changed."
                        onConfirm={() => resetKey.mutate(t.id)}
                      >
                        <Tooltip title="Reset host key"><Button size="small" icon={<KeyOutlined />} /></Tooltip>
                      </Popconfirm>
                    )}
                    <Popconfirm
                      title="Delete target?"
                      description="Its accounts and stored secrets are deleted too."
                      onConfirm={() => remove.mutate(t.id)}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                ),
              }]
            : []),
        ]}
      />
      {editing !== undefined && <TargetModal target={editing} onClose={() => setEditing(undefined)} />}
    </>
  );
}
