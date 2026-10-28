import { zodResolver } from '@hookform/resolvers/zod';
import { Input, InputNumber, Modal, Select } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { PLATFORMS, Protocol } from '@/constants/enums/inventory';
import { useSaveTarget } from '@/features/inventory/hooks';
import {
  targetFormSchema,
  targetFormValuesFrom,
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

  useEffect(() => {
    if (open) reset(targetFormValuesFrom(target));
  }, [open, target, reset]);

  const onSubmit = async (values: TargetFormValues) => {
    try {
      await saveTarget({ id: target?.id, payload: { ...values, port: values.port ?? undefined } });
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
        <FormField label="Tags" htmlFor="target-tags">
          <Controller
            control={control}
            name="tags"
            render={({ field }) => (
              <Select {...field} id="target-tags" className="w-full" mode="tags" tokenSeparators={[',']} />
            )}
          />
        </FormField>
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
