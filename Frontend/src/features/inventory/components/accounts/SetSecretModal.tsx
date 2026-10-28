import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal } from 'antd';
import { useEffect, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle, Text } from '@/components';
import { useSetAccountSecret } from '@/features/inventory/hooks';
import {
  secretFormDefaults,
  secretFormSchema,
  type SecretFormValues,
} from '@/features/inventory/schemas/accountSchema';
import { isSnmpType } from '@/constants/enums/inventory';
import type { Account, SnmpSecret } from '@/services/inventory-services';
import { emptySnmpSecret, SnmpSecretFields, snmpPayload } from './SnmpSecretFields';
import { notify } from '@/utils/notify';

export function SetSecretModal({ account, onClose }: { account: Account | null; onClose: () => void }) {
  const { mutateAsync: setSecret, isPending } = useSetAccountSecret();
  const { control, handleSubmit, reset, watch } = useForm<SecretFormValues>({
    resolver: zodResolver(secretFormSchema),
    defaultValues: secretFormDefaults,
  });
  const value = watch('value');
  const snmp = isSnmpType(account?.secret_type);
  const [snmpSecret, setSnmpSecret] = useState<SnmpSecret>(emptySnmpSecret('snmp_v2c'));

  useEffect(() => {
    if (account) reset(secretFormDefaults);
    if (account && isSnmpType(account.secret_type)) setSnmpSecret(emptySnmpSecret(account.secret_type));
  }, [account, reset]);

  const saveSnmp = async () => {
    if (!account) return;
    try {
      await setSecret({ id: account.id, value: snmpPayload(snmpSecret) });
      notify.success('Secret stored as a new version');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

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
        {snmp ? (
          <SnmpSecretFields value={snmpSecret} onChange={setSnmpSecret} />
        ) : (
          <FormField label="Secret" htmlFor="account-secret-value">
            <Controller
              control={control}
              name="value"
              render={({ field }) => <Input.Password {...field} id="account-secret-value" autoComplete="new-password" />}
            />
          </FormField>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="small"
            disabled={!snmp && !value}
            loading={isPending}
            onClick={snmp ? () => void saveSnmp() : handleSubmit(onSubmit)}
          >
            Save
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default SetSecretModal;
