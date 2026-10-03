import { DeleteOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { errorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import { directoryApi } from '@/services/api';
import type { DirectoryConfig, DirectoryTestResult, SyncResult } from '@/types/api';
import { fromNow } from '@/lib/format';

const PRESETS = {
  ad: {
    label: 'Active Directory',
    user_filter: '(&(objectClass=user)(sAMAccountName={username}))',
    attr_username: 'sAMAccountName',
    attr_email: 'mail',
    attr_full_name: 'displayName',
    group_base_dn: '',
    group_filter: '',
  },
  openldap: {
    label: 'OpenLDAP',
    user_filter: '(&(objectClass=inetOrgPerson)(uid={username}))',
    attr_username: 'uid',
    attr_email: 'mail',
    attr_full_name: 'cn',
    group_base_dn: '',
    group_filter: '(&(objectClass=groupOfNames)(member={user_dn}))',
  },
} as const;

const ROLE_VALUES = ['admin', 'approver', 'auditor', 'user'] as const;
const ROLES = ROLE_VALUES.map((r) => ({ value: r, label: r }));

const schema = z.object({
  enabled: z.boolean(),
  server_url: z.string().regex(/^ldaps?:\/\/\S+$/, 'ldap://host:389 or ldaps://host:636'),
  start_tls: z.boolean(),
  verify_tls: z.boolean(),
  ca_cert_pem: z.string().optional(),
  bind_dn: z.string().min(3, 'Required'),
  bind_password: z.string().optional(),
  user_base_dn: z.string().min(3, 'Required'),
  user_filter: z.string().refine((v) => v.includes('{username}'), 'Must contain {username}'),
  attr_username: z.string().min(1),
  attr_email: z.string().min(1),
  attr_full_name: z.string().min(1),
  group_base_dn: z.string().optional(),
  group_filter: z.string().optional(),
  role_mappings: z.array(z.object({ group_dn: z.string().min(3, 'Group DN'), role: z.enum(ROLE_VALUES) })),
  default_role: z.enum(ROLE_VALUES).nullable(),
  timeout_seconds: z.number().int().min(1).max(60),
  sync_interval_minutes: z.number().int().min(0).max(1440).refine((v) => v === 0 || v >= 5, '0 (off) or at least 5'),
  sync_max_disable_percent: z.number().int().min(1).max(100),
});
type Values = z.infer<typeof schema>;

const toValues = (c: DirectoryConfig | null): Values => ({
  enabled: c?.enabled ?? false,
  server_url: c?.server_url ?? 'ldaps://dc01.corp.example:636',
  start_tls: c?.start_tls ?? false,
  verify_tls: c?.verify_tls ?? true,
  ca_cert_pem: c?.ca_cert_pem ?? '',
  bind_dn: c?.bind_dn ?? '',
  bind_password: '',
  user_base_dn: c?.user_base_dn ?? '',
  user_filter: c?.user_filter ?? PRESETS.ad.user_filter,
  attr_username: c?.attr_username ?? PRESETS.ad.attr_username,
  attr_email: c?.attr_email ?? 'mail',
  attr_full_name: c?.attr_full_name ?? 'displayName',
  group_base_dn: c?.group_base_dn ?? '',
  group_filter: c?.group_filter ?? '',
  role_mappings: c?.role_mappings ?? [],
  default_role: c?.default_role ?? null,
  timeout_seconds: c?.timeout_seconds ?? 10,
  sync_interval_minutes: c?.sync_interval_minutes ?? 60,
  sync_max_disable_percent: c?.sync_max_disable_percent ?? 20,
});

const text = (f: { value: unknown; onChange: (v: unknown) => void }, placeholder?: string, mono = true) => (
  <Input
    className={mono ? 'font-mono' : undefined}
    placeholder={placeholder}
    value={(f.value as string) ?? ''}
    onChange={(e) => f.onChange(e.target.value)}
  />
);

function TestUser() {
  const [username, setUsername] = useState('');
  const test = useMutation({ mutationFn: async (u: string) => (await directoryApi.test(u)).data });
  const r: DirectoryTestResult | undefined = test.data;
  return (
    <Card size="small" title="Test a user (no password needed)">
      <Space.Compact block>
        <Input placeholder="Login name, e.g. jdoe" value={username} onChange={(e) => setUsername(e.target.value)} onPressEnter={() => username && test.mutate(username)} />
        <Button icon={<SearchOutlined />} disabled={!username} loading={test.isPending} onClick={() => test.mutate(username)}>
          Look up
        </Button>
      </Space.Compact>
      {test.error && <Alert className="!mt-3" type="error" showIcon title={errorMessage(test.error)} />}
      {r && (
        <Descriptions className="!mt-3" size="small" column={1}>
          <Descriptions.Item label="DN"><Typography.Text code>{r.dn}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="Name">{r.full_name ?? '—'} · {r.email ?? 'no e-mail'}</Descriptions.Item>
          <Descriptions.Item label="Groups">
            <Space size={4} wrap>{r.groups.length ? r.groups.map((g) => <Tag key={g}>{g}</Tag>) : '—'}</Space>
          </Descriptions.Item>
          <Descriptions.Item label="WardX role">
            {r.role ? <Tag color="blue">{r.role}</Tag> : <Tag color="red">none — sign-in refused</Tag>}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}

function SyncPanel({ config }: { config: DirectoryConfig }) {
  const { message, modal } = App.useApp();
  const qc = useQueryClient();
  const [shown, setShown] = useState<SyncResult | null>(null);
  const run = useMutation({
    mutationFn: async ({ dryRun, force }: { dryRun: boolean; force?: boolean }) =>
      (await directoryApi.sync(dryRun, force)).data,
    onSuccess: (r) => {
      setShown(r);
      if (!r.dry_run) void qc.invalidateQueries({ queryKey: queryKeys.directory });
      void qc.invalidateQueries({ queryKey: queryKeys.users.all });
    },
    onError: (e) => message.error(errorMessage(e)),
  });
  const r = shown ?? config.last_sync_summary;
  const color = { ok: 'green', needs_review: 'orange', failed: 'red' } as const;

  return (
    <Card
      size="small"
      className="!mt-4"
      title="Directory sync"
      extra={
        <Space>
          <Button size="small" loading={run.isPending} disabled={!config.enabled} onClick={() => run.mutate({ dryRun: true })}>
            Preview
          </Button>
          <Button size="small" type="primary" loading={run.isPending} disabled={!config.enabled} onClick={() => run.mutate({ dryRun: false })}>
            Run now
          </Button>
        </Space>
      }
    >
      <Typography.Text type="secondary">
        {config.sync_interval_minutes ? `Every ${config.sync_interval_minutes} min` : 'Schedule off'} · last run{' '}
        {config.last_sync_at ? fromNow(config.last_sync_at) : 'never'}
      </Typography.Text>
      {r && (
        <div className="mt-3 space-y-2">
          <Space wrap>
            <Tag color={color[r.status]}>{r.dry_run ? `preview: ${r.status}` : r.status}</Tag>
            <span>{r.checked} checked</span>
          </Space>
          {r.disabled.length > 0 && (
            <div>
              <b>{r.dry_run || r.status !== 'ok' ? 'Would disable' : 'Disabled'}:</b>{' '}
              {r.disabled.map((d) => <Tag key={d.username} color="red" title={d.reason}>{d.username}</Tag>)}
            </div>
          )}
          {r.enabled.length > 0 && <div><b>Re-enabled:</b> {r.enabled.map((u) => <Tag key={u} color="green">{u}</Tag>)}</div>}
          {r.role_changes.length > 0 && (
            <div><b>Role changes:</b> {r.role_changes.map((c) => <Tag key={c.username}>{c.username}: {c.from} → {c.to}</Tag>)}</div>
          )}
          {(r.revoked_checkouts > 0 || r.killed_sessions > 0) && (
            <div>Revoked {r.revoked_checkouts} check-out(s), ended {r.killed_sessions} live session(s).</div>
          )}
          {r.problems.map((p) => <Alert key={p} type={r.status === 'ok' ? 'info' : 'warning'} showIcon title={p} />)}
          {r.status === 'needs_review' && !r.dry_run && (
            <Button
              danger
              size="small"
              onClick={() =>
                modal.confirm({
                  title: `Disable ${r.disabled.length} users?`,
                  content: 'Only if you have checked the list and these people really left.',
                  okText: 'Apply anyway',
                  okButtonProps: { danger: true },
                  onOk: () => run.mutateAsync({ dryRun: false, force: true }),
                })
              }
            >
              Apply anyway
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

function ConfigForm({ config }: { config: DirectoryConfig | null }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { control, handleSubmit, setValue, watch } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(config),
  });
  const mappings = useFieldArray({ control, name: 'role_mappings' });
  const url = watch('server_url');
  const save = useMutation({
    mutationFn: (v: Values) =>
      directoryApi.save({
        ...v,
        ca_cert_pem: v.ca_cert_pem || null,
        bind_password: v.bind_password || undefined,
        group_base_dn: v.group_base_dn || null,
        group_filter: v.group_filter || null,
      }),
    onSuccess: () => {
      message.success('Directory settings saved');
      setValue('bind_password', '');
      void qc.invalidateQueries({ queryKey: queryKeys.directory });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  const applyPreset = (key: keyof typeof PRESETS) => {
    const p = PRESETS[key];
    (['user_filter', 'attr_username', 'attr_email', 'attr_full_name', 'group_base_dn', 'group_filter'] as const).forEach((k) =>
      setValue(k, p[k]),
    );
  };

  return (
    <Form layout="vertical" onFinish={handleSubmit((v) => save.mutate(v))}>
      <Card
        title="Connection"
        extra={
          <FormField control={control} name="enabled" label="" render={(f) => (
            <Switch checkedChildren="enabled" unCheckedChildren="disabled" checked={f.value as boolean} onChange={f.onChange} />
          )} />
        }
        className="!mb-4"
      >
        {url?.startsWith('ldap://') && !watch('start_tls') && (
          <Alert className="!mb-4" type="warning" showIcon title="Plain ldap:// sends passwords unencrypted. Use ldaps:// or turn on StartTLS outside a lab." />
        )}
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField control={control} name="server_url" label="Server URL" render={(f) => text(f, 'ldaps://dc01.corp.example:636')} />
          <div className="grid grid-cols-3 gap-x-4">
            <FormField control={control} name="start_tls" label="StartTLS" render={(f) => <Switch checked={f.value as boolean} onChange={f.onChange} />} />
            <FormField control={control} name="verify_tls" label="Verify certificate" render={(f) => <Switch checked={f.value as boolean} onChange={f.onChange} />} />
            <FormField control={control} name="timeout_seconds" label="Timeout (s)" render={(f) => (
              <InputNumber min={1} max={60} value={f.value as number} onChange={f.onChange} />
            )} />
          </div>
          <FormField control={control} name="bind_dn" label="Service account DN" render={(f) => text(f, 'CN=wardx-svc,OU=Service,DC=corp,DC=example')} />
          <FormField
            control={control}
            name="bind_password"
            label="Service account password"
            extra={config?.has_bind_password ? 'Stored in the vault. Leave blank to keep it.' : 'Stored encrypted in the vault.'}
            render={(f) => <Input.Password autoComplete="new-password" value={(f.value as string) ?? ''} onChange={(e) => f.onChange(e.target.value)} />}
          />
        </div>
        <FormField control={control} name="ca_cert_pem" label="CA certificate (PEM, optional)" render={(f) => (
          <Input.TextArea className="font-mono" rows={2} placeholder="-----BEGIN CERTIFICATE-----" value={(f.value as string) ?? ''} onChange={(e) => f.onChange(e.target.value)} />
        )} />
      </Card>

      <Card
        title="Users"
        extra={
          <Space>
            Preset:
            {Object.entries(PRESETS).map(([k, p]) => (
              <Button key={k} size="small" onClick={() => applyPreset(k as keyof typeof PRESETS)}>{p.label}</Button>
            ))}
          </Space>
        }
        className="!mb-4"
      >
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField control={control} name="user_base_dn" label="User search base" render={(f) => text(f, 'OU=People,DC=corp,DC=example')} />
          <FormField control={control} name="user_filter" label="User filter" render={(f) => text(f)} />
          <FormField control={control} name="attr_username" label="Login name attribute" render={(f) => text(f)} />
          <div className="grid grid-cols-2 gap-x-4">
            <FormField control={control} name="attr_email" label="E-mail attribute" render={(f) => text(f)} />
            <FormField control={control} name="attr_full_name" label="Name attribute" render={(f) => text(f)} />
          </div>
          <FormField control={control} name="group_base_dn" label="Group search base (optional)" extra="Leave both group fields blank to read memberOf (Active Directory)." render={(f) => text(f)} />
          <FormField control={control} name="group_filter" label="Group filter (optional)" render={(f) => text(f, '(&(objectClass=groupOfNames)(member={user_dn}))')} />
        </div>
      </Card>

      <Card title="Groups → WardX roles" className="!mb-4">
        <Typography.Paragraph type="secondary">
          A user in several mapped groups gets the highest role. Roles are refreshed at every sign-in.
        </Typography.Paragraph>
        {mappings.fields.map((m, i) => (
          <div key={m.id} className="mb-2 flex gap-2">
            <div className="flex-1">
              <FormField control={control} name={`role_mappings.${i}.group_dn`} label={i === 0 ? 'Group DN' : ''} render={(f) => text(f, 'CN=PAM-Admins,OU=Groups,DC=corp,DC=example')} />
            </div>
            <div className="w-36">
              <FormField control={control} name={`role_mappings.${i}.role`} label={i === 0 ? 'Role' : ''} render={(f) => (
                <Select options={ROLES} value={f.value as string} onChange={f.onChange} />
              )} />
            </div>
            <Button className={i === 0 ? '!mt-[30px]' : ''} danger icon={<DeleteOutlined />} aria-label="Remove mapping" onClick={() => mappings.remove(i)} />
          </div>
        ))}
        <Button icon={<PlusOutlined />} onClick={() => mappings.append({ group_dn: '', role: 'user' })}>Add mapping</Button>
        <div className="mt-4 max-w-sm">
          <FormField control={control} name="default_role" label="Users in no mapped group" render={(f) => (
            <Select
              value={(f.value as string | null) ?? '__deny'}
              onChange={(v) => f.onChange(v === '__deny' ? null : v)}
              options={[{ value: '__deny', label: 'Refuse sign-in (recommended)' }, ...ROLES]}
            />
          )} />
        </div>
      </Card>

      <Card title="Scheduled sync" className="!mb-4">
        <Typography.Paragraph type="secondary">
          Checks every directory user with the service account. People who left the directory or
          every mapped group are disabled at once: signed out, check-outs revoked, live sessions killed.
        </Typography.Paragraph>
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField control={control} name="sync_interval_minutes" label="Run every (minutes)" extra="0 turns the schedule off" render={(f) => (
            <InputNumber className="!w-full" min={0} max={1440} value={f.value as number} onChange={f.onChange} />
          )} />
          <FormField control={control} name="sync_max_disable_percent" label="Stop if a run would disable more than (%)" extra="Protects against a wrong search base locking everyone out" render={(f) => (
            <InputNumber className="!w-full" min={1} max={100} value={f.value as number} onChange={f.onChange} />
          )} />
        </div>
      </Card>

      <Button type="primary" htmlType="submit" loading={save.isPending}>Save</Button>
    </Form>
  );
}

export default function DirectoryPage() {
  const { data, isLoading } = useQuery({ queryKey: queryKeys.directory, queryFn: async () => (await directoryApi.get()).data });
  return (
    <>
      <Typography.Title level={3} className="!mb-1">Directory sign-in</Typography.Title>
      <Typography.Paragraph type="secondary">
        Let people sign in with their LDAP / Active Directory account. Local WardX accounts keep working
        and always win a name clash. MFA, lockout and auditing apply to directory users too.
      </Typography.Paragraph>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
        <div>{!isLoading && <ConfigForm config={data ?? null} />}</div>
        <div>
          {data && <TestUser />}
          {data && <SyncPanel config={data} />}
        </div>
      </div>
    </>
  );
}
