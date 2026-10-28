import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Input, InputNumber, Modal, Switch } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { useCreateApp, useUpdateApp } from '@/features/provider/hooks';
import {
  appFormSchema,
  appFormValuesFrom,
  parseAllowlist,
  type AppFormValues,
} from '@/features/provider/schemas/appSchema';
import type { AppIdentity, NewAppSecret } from '@/services/provider-services';
import { notify } from '@/utils/notify';

interface AppFormModalProps {
  open: boolean;
  /** When set, edits this app; otherwise creates one (its first secret is then shown once). */
  app?: AppIdentity | null;
  onClose: () => void;
  onCreated: (created: NewAppSecret) => void;
}

export function AppFormModal({ open, app, onClose, onCreated }: AppFormModalProps) {
  const { mutateAsync: createApp, isPending: creating } = useCreateApp();
  const { mutateAsync: updateApp, isPending: updating } = useUpdateApp();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AppFormValues>({ resolver: zodResolver(appFormSchema), defaultValues: appFormValuesFrom(app) });
  const allowlist = useWatch({ control, name: 'ip_allowlist' });

  useEffect(() => {
    if (open) reset(appFormValuesFrom(app));
  }, [open, app, reset]);

  const onSubmit = async (values: AppFormValues) => {
    const payload = {
      ...values,
      description: values.description || null,
      ip_allowlist: parseAllowlist(values.ip_allowlist),
    };
    try {
      if (app) {
        await updateApp({ id: app.id, payload });
        notify.success('Application identity updated');
      } else {
        onCreated(await createApp(payload));
      }
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={open}
      title={<ModalTitle>{app ? `Edit ${app.name}` : 'Add application identity'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <FormField label="Name" htmlFor="app-name" required error={errors.name?.message} hint="e.g. monetx-prod or monetx-collector-karachi">
          <Controller
            control={control}
            name="name"
            render={({ field }) => <Input {...field} id="app-name" status={errors.name ? 'error' : undefined} />}
          />
        </FormField>
        <FormField label="Description" htmlFor="app-description" error={errors.description?.message}>
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} id="app-description" rows={2} />}
          />
        </FormField>
        <FormField
          label="Allowed source networks"
          htmlFor="app-allowlist"
          hint="One CIDR or address per line, e.g. 10.20.0.0/24. Empty means no access."
          error={errors.ip_allowlist?.message}
        >
          <Controller
            control={control}
            name="ip_allowlist"
            render={({ field }) => <Input.TextArea {...field} id="app-allowlist" rows={3} className="font-mono" />}
          />
        </FormField>
        {parseAllowlist(allowlist ?? '').length === 0 && (
          <Alert
            className="!mb-3"
            type="warning"
            showIcon
            title="No allowed networks: this application cannot get a token until you add one."
          />
        )}
        <div className="grid grid-cols-2 gap-4">
          <FormField
            label="Fetches per minute"
            htmlFor="app-rate"
            error={errors.rate_limit_per_minute?.message}
            hint="Across every WardX API worker"
          >
            <Controller
              control={control}
              name="rate_limit_per_minute"
              render={({ field }) => (
                <InputNumber {...field} id="app-rate" className="!w-full" min={1} max={100000} />
              )}
            />
          </FormField>
          <FormField label="Enabled" htmlFor="app-enabled" hint="Disabling ends every token at once">
            <Controller
              control={control}
              name="enabled"
              render={({ field }) => <Switch id="app-enabled" checked={field.value} onChange={field.onChange} />}
            />
          </FormField>
        </div>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={creating || updating} onClick={handleSubmit(onSubmit)}>
            {app ? 'Save' : 'Create'}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default AppFormModal;
