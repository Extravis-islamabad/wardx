import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal, Switch } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { useSaveSafe } from '@/features/safes/hooks';
import { safeFormSchema, safeFormValuesFrom, type SafeFormValues } from '@/features/safes/schemas/safeSchema';
import type { Safe } from '@/services/safes-services';
import { notify } from '@/utils/notify';

interface SafeFormModalProps {
  open: boolean;
  /** When set, the modal edits this safe; otherwise it creates one. */
  safe?: Safe | null;
  onClose: () => void;
}

export function SafeFormModal({ open, safe, onClose }: SafeFormModalProps) {
  const { mutateAsync: saveSafe, isPending } = useSaveSafe();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SafeFormValues>({ resolver: zodResolver(safeFormSchema), defaultValues: safeFormValuesFrom(safe) });

  useEffect(() => {
    if (open) reset(safeFormValuesFrom(safe));
  }, [open, safe, reset]);

  const onSubmit = async (values: SafeFormValues) => {
    try {
      await saveSafe({ id: safe?.id, payload: { ...values, description: values.description || null } });
      notify.success(safe ? 'Safe updated' : 'Safe created');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={open}
      title={<ModalTitle>{safe ? `Edit ${safe.name}` : 'Create safe'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <FormField label="Name" htmlFor="safe-name" required error={errors.name?.message}>
          <Controller
            control={control}
            name="name"
            render={({ field }) => (
              <Input {...field} id="safe-name" autoComplete="off" status={errors.name ? 'error' : undefined} />
            )}
          />
        </FormField>
        <FormField label="Description" htmlFor="safe-description" error={errors.description?.message}>
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} id="safe-description" rows={2} />}
          />
        </FormField>
        <FormField
          label="Active"
          htmlFor="safe-active"
          hint="An inactive safe keeps its members, but nobody uses, retrieves or edits its accounts."
        >
          <Controller
            control={control}
            name="is_active"
            render={({ field }) => <Switch id="safe-active" checked={field.value} onChange={field.onChange} />}
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

export default SafeFormModal;
