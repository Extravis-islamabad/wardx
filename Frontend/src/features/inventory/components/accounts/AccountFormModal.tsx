import { zodResolver } from '@hookform/resolvers/zod';
import { Input, InputNumber, Modal, Select, Switch } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { SECRET_TYPES } from '@/constants/enums/inventory';
import { SafePermission } from '@/constants/enums/safes';
import { PICKER_PAGE } from '@/constants/globals';
import { useCreateAccount, useTargets, useUpdateAccount } from '@/features/inventory/hooks';
import { useSafes } from '@/features/safes/hooks';
import {
  accountFormSchema,
  accountFormValuesFrom,
  type AccountFormValues,
} from '@/features/inventory/schemas/accountSchema';
import type { Account } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

interface AccountFormModalProps {
  open: boolean;
  /** When set, the modal edits this account's policy; otherwise it adds one. */
  account?: Account | null;
  onClose: () => void;
}

export function AccountFormModal({ open, account, onClose }: AccountFormModalProps) {
  const editing = !!account;
  const targets = useTargets(PICKER_PAGE, { enabled: open });
  const safes = useSafes(PICKER_PAGE, { enabled: open });
  // Only safes the user may manage accounts in (both ends of a move need it).
  const manageable = safes.data?.data?.filter(
    (s) => s.is_active && s.my_permissions?.includes(SafePermission.MANAGE_ACCOUNTS),
  );
  const { mutateAsync: createAccount, isPending: creating } = useCreateAccount();
  const { mutateAsync: updateAccount, isPending: updating } = useUpdateAccount();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AccountFormValues>({
    resolver: zodResolver(accountFormSchema),
    defaultValues: accountFormValuesFrom(account),
  });

  useEffect(() => {
    if (open) reset(accountFormValuesFrom(account));
  }, [open, account, reset]);

  const onSubmit = async (values: AccountFormValues) => {
    try {
      if (account) {
        // Target, username and secret type are fixed once the account exists.
        const { safe_id, description, exclusive_checkout, max_checkout_minutes } = values;
        await updateAccount({
          id: account.id,
          payload: { safe_id, description, exclusive_checkout, max_checkout_minutes },
        });
      } else {
        await createAccount({ ...values, secret: values.secret || undefined });
      }
      notify.success(editing ? 'Account updated' : 'Account added');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={open}
      title={
        <ModalTitle>{account ? `Edit ${account.username}@${account.target?.name}` : 'Add privileged account'}</ModalTitle>
      }
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <FormField label="Target" htmlFor="account-target" required error={errors.target_id?.message}>
          <Controller
            control={control}
            name="target_id"
            render={({ field }) => (
              <Select
                {...field}
                id="account-target"
                className="w-full"
                value={field.value || undefined}
                disabled={editing}
                showSearch
                optionFilterProp="label"
                loading={targets.isLoading}
                status={errors.target_id ? 'error' : undefined}
                options={targets.data?.data?.map((t) => ({ value: t.id, label: `${t.name} (${t.address})` }))}
              />
            )}
          />
        </FormField>
        <FormField
          label="Safe"
          htmlFor="account-safe"
          required
          error={errors.safe_id?.message}
          hint={
            editing
              ? "Moving needs manage_accounts on both safes. Approval follows the safe's policy."
              : "Approval follows the safe's policy."
          }
        >
          <Controller
            control={control}
            name="safe_id"
            render={({ field }) => (
              <Select
                {...field}
                id="account-safe"
                className="w-full"
                value={field.value || undefined}
                showSearch
                optionFilterProp="label"
                loading={safes.isLoading}
                status={errors.safe_id ? 'error' : undefined}
                options={[
                  ...(manageable?.map((s) => ({ value: s.id, label: s.name })) ?? []),
                  // Keep the current safe selectable even if it is not in the manageable list.
                  ...(account && !manageable?.some((s) => s.id === account.safe?.id)
                    ? [{ value: account.safe.id, label: account.safe.name }]
                    : []),
                ]}
              />
            )}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Username" htmlFor="account-username" required error={errors.username?.message}>
            <Controller
              control={control}
              name="username"
              render={({ field }) => (
                <Input {...field} id="account-username" disabled={editing} status={errors.username ? 'error' : undefined} />
              )}
            />
          </FormField>
          <FormField label="Secret type" htmlFor="account-secret-type">
            <Controller
              control={control}
              name="secret_type"
              render={({ field }) => (
                <Select {...field} id="account-secret-type" className="w-full" disabled={editing} options={SECRET_TYPES} />
              )}
            />
          </FormField>
        </div>
        {!editing && (
          <FormField
            label="Current secret"
            htmlFor="account-secret"
            hint="Optional; encrypted in the vault, never shown in lists"
            error={errors.secret?.message}
          >
            <Controller
              control={control}
              name="secret"
              render={({ field }) => <Input.Password {...field} id="account-secret" autoComplete="new-password" />}
            />
          </FormField>
        )}
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Exclusive" htmlFor="account-exclusive">
            <Controller
              control={control}
              name="exclusive_checkout"
              render={({ field }) => <Switch id="account-exclusive" checked={field.value} onChange={field.onChange} />}
            />
          </FormField>
          <FormField label="Max minutes" htmlFor="account-max-minutes" error={errors.max_checkout_minutes?.message}>
            <Controller
              control={control}
              name="max_checkout_minutes"
              render={({ field }) => (
                <InputNumber {...field} id="account-max-minutes" className="!w-full" min={1} max={1440} />
              )}
            />
          </FormField>
        </div>
        <FormField label="Description" htmlFor="account-description" error={errors.description?.message}>
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} id="account-description" rows={2} />}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={creating || updating} onClick={handleSubmit(onSubmit)}>
            Save
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default AccountFormModal;
