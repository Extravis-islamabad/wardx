import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle, Text } from '@/components';
import { useSetAccountSecret } from '@/features/inventory/hooks';
import {
  secretFormDefaults,
  secretFormSchema,
  type SecretFormValues,
} from '@/features/inventory/schemas/accountSchema';
import type { Account } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

export function SetSecretModal({ account, onClose }: { account: Account | null; onClose: () => void }) {
  const { mutateAsync: setSecret, isPending } = useSetAccountSecret();
  const { control, handleSubmit, reset, watch } = useForm<SecretFormValues>({
    resolver: zodResolver(secretFormSchema),
    defaultValues: secretFormDefaults,
  });
  const value = watch('value');

  useEffect(() => {
    if (account) reset(secretFormDefaults);
  }, [account, reset]);

  const onSubmit = async (values: SecretFormValues) => {
    if (!account) return;
    try {
      await setSecret({ id: account.id, value: values.value });
      notify.success('Secret stored as a new version');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={!!account}
      title={<ModalTitle>{`Set secret — ${account?.username}@${account?.target?.name}`}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <Text variant="caption" className="mb-3">
          Stores the value the account currently has on the target. It does not change the password on the device.
        </Text>
        <FormField label="Secret" htmlFor="account-secret-value">
          <Controller
            control={control}
            name="value"
            render={({ field }) => <Input.Password {...field} id="account-secret-value" autoComplete="new-password" />}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" disabled={!value} loading={isPending} onClick={handleSubmit(onSubmit)}>
            Save
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default SetSecretModal;
