import { zodResolver } from '@hookform/resolvers/zod';
import { Input, InputNumber, Modal, Select, Switch } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { API_SSL_DEFAULT_PORT, PLATFORMS, Protocol, usesTlsApi } from '@/constants/enums/inventory';
import { useSaveTarget } from '@/features/inventory/hooks';
import {
  targetFormSchema,
  targetFormValuesFrom,
  targetPayloadFrom,
  type TargetFormValues,
} from '@/features/inventory/schemas/targetSchema';
import type { Target } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

const PROTOCOL_OPTIONS = Object.values(Protocol).map((p) => ({ value: p, label: p.toUpperCase() }));

interface TargetFormModalProps {
  open: boolean;
  /** When set, the modal edits this target; otherwise it adds one. */
  target?: Target | null;
  onClose: () => void;
}

export function TargetFormModal({ open, target, onClose }: TargetFormModalProps) {
  const { mutateAsync: saveTarget, isPending } = useSaveTarget();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TargetFormValues>({
    resolver: zodResolver(targetFormSchema),
    defaultValues: targetFormValuesFrom(target),
  });

  const platform = useWatch({ control, name: 'platform' });

  useEffect(() => {
    if (open) reset(targetFormValuesFrom(target));
  }, [open, target, reset]);

  const onSubmit = async (values: TargetFormValues) => {
    try {
      await saveTarget({ id: target?.id, payload: targetPayloadFrom(values, target) });
      notify.success(target ? 'Target updated' : 'Target added');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={open}
      title={<ModalTitle>{target ? `Edit ${target.name}` : 'Add target'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <FormField label="Name" htmlFor="target-name" required error={errors.name?.message}>
          <Controller
            control={control}
            name="name"
            render={({ field }) => (
              <Input {...field} id="target-name" status={errors.name ? 'error' : undefined} />
            )}
          />
        </FormField>
        <FormField label="Address (IP or hostname)" htmlFor="target-address" required error={errors.address?.message}>
          <Controller
            control={control}
            name="address"
            render={({ field }) => (
              <Input {...field} id="target-address" status={errors.address ? 'error' : undefined} />
            )}
          />
        </FormField>
        <FormField label="Platform" htmlFor="target-platform" required error={errors.platform?.message}>
          <Controller
            control={control}
            name="platform"
            render={({ field }) => (
              <Select {...field} id="target-platform" className="w-full" options={PLATFORMS} showSearch optionFilterProp="label" />
            )}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Protocol" htmlFor="target-protocol" error={errors.protocol?.message}>
            <Controller
              control={control}
              name="protocol"
              render={({ field }) => (
                <Select {...field} id="target-protocol" className="w-full" options={PROTOCOL_OPTIONS} />
              )}
            />
          </FormField>
          <FormField label="Port" htmlFor="target-port" hint="Blank = protocol default" error={errors.port?.message}>
            <Controller
              control={control}
              name="port"
              render={({ field }) => (
                <InputNumber {...field} id="target-port" className="!w-full" min={1} max={65535} />
              )}
            />
          </FormField>
        </div>
        {usesTlsApi(platform) && (
          <div className="grid grid-cols-2 gap-4">
            <FormField
              label="API-SSL port"
              htmlFor="target-api-port"
              hint={`Blank = ${API_SSL_DEFAULT_PORT}. Passwords change only over API-SSL with a pinned certificate.`}
              error={errors.api_port?.message}
            >
              <Controller
                control={control}
                name="api_port"
                render={({ field }) => (
                  <InputNumber {...field} id="target-api-port" className="!w-full" min={1} max={65535} />
                )}
              />
            </FormField>
            <FormField
              label="API is TLS (API-SSL)"
              htmlFor="target-api-tls"
              hint="Off: the device offers only the cleartext API (8728). It can be vaulted, never rotated."
            >
              <Controller
                control={control}
                name="api_tls"
                render={({ field }) => <Switch id="target-api-tls" checked={field.value} onChange={field.onChange} />}
              />
            </FormField>
          </div>
        )}
        <FormField label="Tags" htmlFor="target-tags">
          <Controller
            control={control}
            name="tags"
            render={({ field }) => (
              <Select {...field} id="target-tags" className="w-full" mode="tags" tokenSeparators={[',']} />
            )}
          />
        </FormField>
        <FormField
          label="Password rotation allowed"
          htmlFor="target-rotation"
          hint={
            target?.non_rotatable_reason
              ? `This target is ${target.non_rotatable_reason}.`
              : 'Off by default. WardX also needs rotation switched on (WARDX_ROTATION_ENABLED).'
          }
        >
          <Controller
            control={control}
            name="rotation_allowed"
            render={({ field }) => (
              <Switch id="target-rotation" checked={field.value} onChange={field.onChange} />
            )}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Min password length" htmlFor="target-minlen" hint="Blank: platform default" error={errors.min_length?.message}>
            <Controller
              control={control}
              name="min_length"
              render={({ field }) => <InputNumber {...field} id="target-minlen" className="!w-full" min={12} max={128} />}
            />
          </FormField>
          <FormField label="Max password length (device cap)" htmlFor="target-maxlen" hint="e.g. older IOS: 25" error={errors.max_length?.message}>
            <Controller
              control={control}
              name="max_length"
              render={({ field }) => <InputNumber {...field} id="target-maxlen" className="!w-full" min={12} max={128} />}
            />
          </FormField>
        </div>
        <FormField label="Description" htmlFor="target-description" error={errors.description?.message}>
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} id="target-description" rows={2} />}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
            Save
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default TargetFormModal;
