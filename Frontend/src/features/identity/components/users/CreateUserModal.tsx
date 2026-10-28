import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal, Select } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { ROLE_OPTIONS } from '@/features/identity/constants';
import { useCreateUser } from '@/features/identity/hooks';
import { userFormDefaults, userFormSchema, type UserFormValues } from '@/features/identity/schemas/userSchema';
import { notify } from '@/utils/notify';

export function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { mutateAsync: createUser, isPending } = useCreateUser();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UserFormValues>({
    resolver: zodResolver(userFormSchema),
    defaultValues: userFormDefaults,
  });

  useEffect(() => {
    if (open) reset(userFormDefaults);
  }, [open, reset]);

  const onSubmit = async (values: UserFormValues) => {
    try {
      await createUser({ ...values, email: values.email || undefined });
      notify.success('User created');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal open={open} title={<ModalTitle>Add user</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        <FormField label="Username" htmlFor="user-username" required error={errors.username?.message}>
          <Controller
            control={control}
            name="username"
            render={({ field }) => (
              <Input {...field} id="user-username" autoComplete="off" status={errors.username ? 'error' : undefined} />
            )}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Full name" htmlFor="user-full-name" error={errors.full_name?.message}>
            <Controller
              control={control}
              name="full_name"
              render={({ field }) => <Input {...field} id="user-full-name" />}
            />
          </FormField>
          <FormField label="Email" htmlFor="user-email" error={errors.email?.message}>
            <Controller
              control={control}
              name="email"
              render={({ field }) => (
                <Input {...field} id="user-email" status={errors.email ? 'error' : undefined} />
              )}
            />
          </FormField>
        </div>
        <FormField label="Role" htmlFor="user-role" required>
          <Controller
            control={control}
            name="role"
            render={({ field }) => <Select {...field} id="user-role" className="w-full" options={ROLE_OPTIONS} />}
          />
        </FormField>
        <FormField label="Initial password" htmlFor="user-password" required error={errors.password?.message}>
          <Controller
            control={control}
            name="password"
            render={({ field }) => (
              <Input.Password
                {...field}
                id="user-password"
                autoComplete="new-password"
                status={errors.password ? 'error' : undefined}
              />
            )}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
            OK
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default CreateUserModal;
