import { DeleteOutlined, ExperimentOutlined, PlusOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { PLATFORMS, Role, platformLabel } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { errorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import { rulesApi, targetsApi } from '@/services/api';
import type { CommandRule } from '@/types/api';

const isRegex = (v: string) => {
  try {
    new RegExp(v);
    return true;
  } catch {
    return false;
  }
};

const schema = z.object({
  pattern: z.string().min(1, 'Required').max(500).refine(isRegex, 'Not a valid regular expression'),
  description: z.string().max(500).optional(),
  scope: z.enum(['global', 'platform', 'target']),
  platform: z.string().optional(),
  target_id: z.string().optional(),
});
type Values = z.infer<typeof schema>;

function RuleModal({ onClose }: { onClose: () => void }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { control, handleSubmit, watch } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { pattern: '', description: '', scope: 'global' },
  });
  const scope = watch('scope');
  const targets = useQuery({
    queryKey: queryKeys.targets.list({ page: 1, page_size: 200 }),
    queryFn: () => targetsApi.list({ page: 1, page_size: 200 }),
    enabled: scope === 'target',
  });
  const create = useMutation({
    mutationFn: (v: Values) =>
      rulesApi.create({
        pattern: v.pattern,
        description: v.description || undefined,
        platform: v.scope === 'platform' ? v.platform : undefined,
        target_id: v.scope === 'target' ? v.target_id : undefined,
      }),
    onSuccess: () => {
      message.success('Rule added; it applies to sessions that start from now');
      void qc.invalidateQueries({ queryKey: queryKeys.rules });
      onClose();
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <Modal open title="Add deny rule" onCancel={onClose} onOk={handleSubmit((v) => create.mutate(v))} confirmLoading={create.isPending} okText="Add rule">
      <Form layout="vertical">
        <FormField control={control} name="pattern" label="Pattern (regular expression, case-insensitive)" extra="Matched against the typed command with spaces collapsed, e.g. ^(reload|write erase)\b" render={(f) => (
          <Input className="font-mono" value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <FormField control={control} name="description" label="Shown to the user when blocked" render={(f) => (
          <Input value={f.value as string} onChange={(e) => f.onChange(e.target.value)} />
        )} />
        <FormField control={control} name="scope" label="Applies to" render={(f) => (
          <Select value={f.value as string} onChange={f.onChange} options={[
            { value: 'global', label: 'Every session' },
            { value: 'platform', label: 'One platform' },
            { value: 'target', label: 'One target' },
          ]} />
        )} />
        {scope === 'platform' && (
          <FormField control={control} name="platform" label="Platform" render={(f) => (
            <Select options={PLATFORMS} value={f.value as string} onChange={f.onChange} showSearch optionFilterProp="label" />
          )} />
        )}
        {scope === 'target' && (
          <FormField control={control} name="target_id" label="Target" render={(f) => (
            <Select
              value={f.value as string}
              onChange={f.onChange}
              showSearch
              optionFilterProp="label"
              loading={targets.isLoading}
              options={targets.data?.data.map((t) => ({ value: t.id, label: `${t.name} (${t.address})` }))}
            />
          )} />
        )}
      </Form>
    </Modal>
  );
}

function RuleTester() {
  const [command, setCommand] = useState('');
  const test = useMutation({ mutationFn: async (c: string) => (await rulesApi.test(c)).data });
  return (
    <Card size="small" title={<><ExperimentOutlined /> Try a command</>} className="!mb-4">
      <Space.Compact block>
        <Input
          className="font-mono"
          placeholder="reload in 5"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onPressEnter={() => command && test.mutate(command)}
        />
        <Button onClick={() => test.mutate(command)} disabled={!command} loading={test.isPending}>Test</Button>
      </Space.Compact>
      {test.data && (
        <Alert
          className="!mt-3"
          showIcon
          type={test.data.blocked ? 'error' : 'success'}
          title={test.data.blocked ? `Blocked: ${test.data.description ?? 'matches a deny rule'}` : 'Allowed by every active rule'}
        />
      )}
    </Card>
  );
}

export default function CommandRulesPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole(Role.Admin);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: queryKeys.rules, queryFn: async () => (await rulesApi.list()).data });
  const targets = useQuery({
    queryKey: queryKeys.targets.list({ page: 1, page_size: 200 }),
    queryFn: () => targetsApi.list({ page: 1, page_size: 200 }),
  });
  const targetName = (id: string) => targets.data?.data.find((t) => t.id === id)?.name ?? 'target';

  const onDone = () => void qc.invalidateQueries({ queryKey: queryKeys.rules });
  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => rulesApi.update(id, { is_active }),
    onSuccess: onDone,
    onError: (e) => message.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: (id: string) => rulesApi.remove(id), onSuccess: onDone, onError: (e) => message.error(errorMessage(e)) });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Typography.Title level={3} className="!m-0">Command policy</Typography.Title>
          <Typography.Text type="secondary">
            Commands matching a rule are erased on the device before they run. Sessions with rules
            have arrow keys, history and tab completion turned off so commands cannot slip past.
          </Typography.Text>
        </div>
        {isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>Add rule</Button>}
      </div>
      <RuleTester />
      <Table<CommandRule>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        pagination={false}
        columns={[
          { title: 'Pattern', dataIndex: 'pattern', render: (p: string) => <code>{p}</code> },
          { title: 'Message', dataIndex: 'description', render: (d: string | null) => d ?? '—' },
          {
            title: 'Applies to',
            render: (_, r) =>
              r.platform ? <Tag>{platformLabel(r.platform)}</Tag> : r.target_id ? <Tag color="blue">{targetName(r.target_id)}</Tag> : r.account_id ? <Tag color="purple">one account</Tag> : <Tag color="gold">everything</Tag>,
          },
          {
            title: 'Active',
            render: (_, r) => <Switch size="small" checked={r.is_active} disabled={!isAdmin} onChange={(is_active) => toggle.mutate({ id: r.id, is_active })} />,
          },
          ...(isAdmin
            ? [{
                title: '',
                width: 60,
                render: (_: unknown, r: CommandRule) => (
                  <Popconfirm title="Delete this rule?" onConfirm={() => remove.mutate(r.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                ),
              }]
            : []),
        ]}
      />
      {adding && <RuleModal onClose={() => setAdding(false)} />}
    </>
  );
}
