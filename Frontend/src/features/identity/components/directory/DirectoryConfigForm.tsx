import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Card, Input, InputNumber, Select, Space, Switch, Typography } from 'antd';
import { Controller, useFieldArray, useForm, type Control, type FieldPath } from 'react-hook-form';
import { Button, FormField } from '@/components';
import { Role } from '@/constants/enums/auth';
import {
  DENY_DEFAULT_ROLE,
  DIRECTORY_PRESETS,
  ROLE_SHORT_OPTIONS,
  type DirectoryPreset,
} from '@/features/identity/constants';
import { useSaveDirectoryConfig } from '@/features/identity/hooks';
import {
  directoryFormSchema,
  directoryFormValuesFrom,
  type DirectoryFormValues,
} from '@/features/identity/schemas/directorySchema';
import type { DirectoryConfig } from '@/services/identity-services';
import { notify } from '@/utils/notify';

const PRESET_FIELDS = ['user_filter', 'attr_username', 'attr_email', 'attr_full_name', 'group_base_dn', 'group_filter'] as const;

type TextFieldName = Extract<
  FieldPath<DirectoryFormValues>,
  | 'server_url'
  | 'bind_dn'
  | 'user_base_dn'
  | 'user_filter'
  | 'attr_username'
  | 'attr_email'
  | 'attr_full_name'
  | 'group_base_dn'
  | 'group_filter'
  | `role_mappings.${number}.group_dn`
>;

/** A monospace text input bound to one directory setting. */
const DnInput = ({
  control,
  name,
  placeholder,
  invalid,
}: {
  control: Control<DirectoryFormValues>;
  name: TextFieldName;
  placeholder?: string;
  invalid?: boolean;
}) => (
  <Controller
    control={control}
    name={name}
    render={({ field }) => (
      <Input
        {...field}
        id={name}
        value={field.value ?? ''}
        className="font-mono"
        placeholder={placeholder}
        status={invalid ? 'error' : undefined}
      />
    )}
  />
);

export function DirectoryConfigForm({ config }: { config: DirectoryConfig | null }) {
  const { mutateAsync: saveConfig, isPending } = useSaveDirectoryConfig();
  const {
    control,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<DirectoryFormValues>({
    resolver: zodResolver(directoryFormSchema),
    defaultValues: directoryFormValuesFrom(config),
  });
  const mappings = useFieldArray({ control, name: 'role_mappings' });
  const url = watch('server_url');
  const startTls = watch('start_tls');

  const onSubmit = async (values: DirectoryFormValues) => {
    try {
      await saveConfig({
        ...values,
        ca_cert_pem: values.ca_cert_pem || null,
        bind_password: values.bind_password || undefined,
        group_base_dn: values.group_base_dn || null,
        group_filter: values.group_filter || null,
      });
      notify.success('Directory settings saved');
      setValue('bind_password', '');
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const applyPreset = (key: DirectoryPreset) => {
    const preset = DIRECTORY_PRESETS[key];
    PRESET_FIELDS.forEach((k) => setValue(k, preset[k]));
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <Card
        title="Connection"
        extra={
          <Controller
            control={control}
            name="enabled"
            render={({ field }) => (
              <Switch
                aria-label="Directory sign-in enabled"
                checkedChildren="enabled"
                unCheckedChildren="disabled"
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />
        }
        className="!mb-4"
      >
        {url?.startsWith('ldap://') && !startTls && (
          <Alert
            className="!mb-4"
            type="warning"
            showIcon
            title="Plain ldap:// sends passwords unencrypted. Use ldaps:// or turn on StartTLS outside a lab."
          />
        )}
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField label="Server URL" htmlFor="server_url" error={errors.server_url?.message}>
            <DnInput control={control} name="server_url" placeholder="ldaps://dc01.corp.example:636" invalid={!!errors.server_url} />
          </FormField>
          <div className="grid grid-cols-3 gap-x-4">
            <FormField label="StartTLS" htmlFor="start_tls">
              <Controller
                control={control}
                name="start_tls"
                render={({ field }) => <Switch id="start_tls" checked={field.value} onChange={field.onChange} />}
              />
            </FormField>
            <FormField label="Verify certificate" htmlFor="verify_tls">
              <Controller
                control={control}
                name="verify_tls"
                render={({ field }) => <Switch id="verify_tls" checked={field.value} onChange={field.onChange} />}
              />
            </FormField>
            <FormField label="Timeout (s)" htmlFor="timeout_seconds" error={errors.timeout_seconds?.message}>
              <Controller
                control={control}
                name="timeout_seconds"
                render={({ field }) => <InputNumber {...field} id="timeout_seconds" min={1} max={60} />}
              />
            </FormField>
          </div>
          <FormField label="Service account DN" htmlFor="bind_dn" error={errors.bind_dn?.message}>
            <DnInput
              control={control}
              name="bind_dn"
              placeholder="CN=wardx-svc,OU=Service,DC=corp,DC=example"
              invalid={!!errors.bind_dn}
            />
          </FormField>
          <FormField
            label="Service account password"
            htmlFor="bind_password"
            hint={config?.has_bind_password ? 'Stored in the vault. Leave blank to keep it.' : 'Stored encrypted in the vault.'}
          >
            <Controller
              control={control}
              name="bind_password"
              render={({ field }) => (
                <Input.Password {...field} id="bind_password" value={field.value ?? ''} autoComplete="new-password" />
              )}
            />
          </FormField>
        </div>
        <FormField label="CA certificate (PEM, optional)" htmlFor="ca_cert_pem">
          <Controller
            control={control}
            name="ca_cert_pem"
            render={({ field }) => (
              <Input.TextArea
                {...field}
                id="ca_cert_pem"
                value={field.value ?? ''}
                className="font-mono"
                rows={2}
                placeholder="-----BEGIN CERTIFICATE-----"
              />
            )}
          />
        </FormField>
      </Card>

      <Card
        title="Users"
        extra={
          <Space>
            Preset:
            {Object.entries(DIRECTORY_PRESETS)?.map(([k, p]) => (
              <Button key={k} variant="admin" size="small" onClick={() => applyPreset(k as DirectoryPreset)}>
                {p.label}
              </Button>
            ))}
          </Space>
        }
        className="!mb-4"
      >
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField label="User search base" htmlFor="user_base_dn" error={errors.user_base_dn?.message}>
            <DnInput control={control} name="user_base_dn" placeholder="OU=People,DC=corp,DC=example" invalid={!!errors.user_base_dn} />
          </FormField>
          <FormField label="User filter" htmlFor="user_filter" error={errors.user_filter?.message}>
            <DnInput control={control} name="user_filter" invalid={!!errors.user_filter} />
          </FormField>
          <FormField label="Login name attribute" htmlFor="attr_username" error={errors.attr_username?.message}>
            <DnInput control={control} name="attr_username" invalid={!!errors.attr_username} />
          </FormField>
          <div className="grid grid-cols-2 gap-x-4">
            <FormField label="E-mail attribute" htmlFor="attr_email" error={errors.attr_email?.message}>
              <DnInput control={control} name="attr_email" invalid={!!errors.attr_email} />
            </FormField>
            <FormField label="Name attribute" htmlFor="attr_full_name" error={errors.attr_full_name?.message}>
              <DnInput control={control} name="attr_full_name" invalid={!!errors.attr_full_name} />
            </FormField>
          </div>
          <FormField
            label="Group search base (optional)"
            htmlFor="group_base_dn"
            hint="Leave both group fields blank to read memberOf (Active Directory)."
          >
            <DnInput control={control} name="group_base_dn" />
          </FormField>
          <FormField label="Group filter (optional)" htmlFor="group_filter">
            <DnInput control={control} name="group_filter" placeholder="(&(objectClass=groupOfNames)(member={user_dn}))" />
          </FormField>
        </div>
      </Card>

      <Card title="Groups → WardX roles" className="!mb-4">
        <Typography.Paragraph type="secondary">
          A user in several mapped groups gets the highest role. Roles are refreshed at every sign-in.
        </Typography.Paragraph>
        {mappings.fields?.map((m, i) => (
          <div key={m.id} className="mb-2 flex items-end gap-2">
            <FormField
              className="flex-1"
              label={i === 0 ? 'Group DN' : undefined}
              htmlFor={`role_mappings.${i}.group_dn`}
              error={errors.role_mappings?.[i]?.group_dn?.message}
            >
              <DnInput
                control={control}
                name={`role_mappings.${i}.group_dn`}
                placeholder="CN=PAM-Admins,OU=Groups,DC=corp,DC=example"
                invalid={!!errors.role_mappings?.[i]?.group_dn}
              />
            </FormField>
            <FormField className="w-36" label={i === 0 ? 'Role' : undefined} htmlFor={`role_mappings.${i}.role`}>
              <Controller
                control={control}
                name={`role_mappings.${i}.role`}
                render={({ field }) => (
                  <Select {...field} id={`role_mappings.${i}.role`} className="w-full" options={ROLE_SHORT_OPTIONS} />
                )}
              />
            </FormField>
            <Button variant="danger" size="small" aria-label="Remove mapping" onClick={() => mappings.remove(i)}>
              Remove
            </Button>
          </div>
        ))}
        <Button variant="admin" onClick={() => mappings.append({ group_dn: '', role: Role.USER })}>
          Add mapping
        </Button>
        <div className="mt-4 max-w-sm">
          <FormField label="Users in no mapped group" htmlFor="default_role">
            <Controller
              control={control}
              name="default_role"
              render={({ field }) => (
                <Select
                  id="default_role"
                  className="w-full"
                  value={field.value ?? DENY_DEFAULT_ROLE}
                  onChange={(v: string) => field.onChange(v === DENY_DEFAULT_ROLE ? null : v)}
                  options={[{ value: DENY_DEFAULT_ROLE, label: 'Refuse sign-in (recommended)' }, ...ROLE_SHORT_OPTIONS]}
                />
              )}
            />
          </FormField>
        </div>
      </Card>

      <Card title="Scheduled sync" className="!mb-4">
        <Typography.Paragraph type="secondary">
          Checks every directory user with the service account. People who left the directory or every mapped group are
          disabled at once: signed out, check-outs revoked, live sessions killed.
        </Typography.Paragraph>
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormField
            label="Run every (minutes)"
            htmlFor="sync_interval_minutes"
            hint="0 turns the schedule off"
            error={errors.sync_interval_minutes?.message}
          >
            <Controller
              control={control}
              name="sync_interval_minutes"
              render={({ field }) => (
                <InputNumber {...field} id="sync_interval_minutes" className="!w-full" min={0} max={1440} />
              )}
            />
          </FormField>
          <FormField
            label="Stop if a run would disable more than (%)"
            htmlFor="sync_max_disable_percent"
            hint="Protects against a wrong search base locking everyone out"
            error={errors.sync_max_disable_percent?.message}
          >
            <Controller
              control={control}
              name="sync_max_disable_percent"
              render={({ field }) => (
                <InputNumber {...field} id="sync_max_disable_percent" className="!w-full" min={1} max={100} />
              )}
            />
          </FormField>
        </div>
      </Card>

      <Button variant="primary" type="submit" loading={isPending}>
        Save
      </Button>
    </form>
  );
}

export default DirectoryConfigForm;
