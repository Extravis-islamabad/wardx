import { zodResolver } from '@hookform/resolvers/zod';
import { Input, InputNumber, Modal } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import { useCreateCheckout, useCreateRequest } from '@/features/access/hooks';
import {
  accessFormDefaults,
  accessFormSchema,
  type AccessFormValues,
} from '@/features/access/schemas/accessSchema';
import type { Checkout } from '@/services/access-services';
import type { Account } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

interface RequestAccessModalProps {
  account: Account | null;
  onClose: () => void;
  /** A direct check-out (no approval needed) hands the new check-out back for revealing. */
  onCheckedOut: (checkout: Checkout) => void;
}

/** Checks an account out directly, or files an approval request when its policy needs one. */
export function RequestAccessModal({ account, onClose, onCheckedOut }: RequestAccessModalProps) {
  const navigate = useNavigate();
  const needsApproval = !!account?.requires_approval;
  const { mutateAsync: createRequest, isPending: requesting } = useCreateRequest();
  const { mutateAsync: createCheckout, isPending: checkingOut } = useCreateCheckout();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AccessFormValues>({
    resolver: zodResolver(accessFormSchema),
    defaultValues: accessFormDefaults(account?.max_checkout_minutes),
  });

  useEffect(() => {
    if (account) reset(accessFormDefaults(account.max_checkout_minutes));
  }, [account, reset]);

  const onSubmit = async (values: AccessFormValues) => {
    if (!account) return;
    try {
      if (needsApproval) {
        await createRequest({ account_id: account.id, ...values, ticket_ref: values.ticket_ref || undefined });
        onClose();
        notify.success('Request sent for approval');
        navigate(ROUTES.REQUESTS);
      } else {
        const checkout = await createCheckout({
          account_id: account.id,
          reason: values.reason,
          duration_minutes: values.duration_minutes,
        });
        onClose();
        notify.success('Checked out');
        onCheckedOut(checkout);
      }
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal
      open={!!account}
      title={
        <ModalTitle>{`${needsApproval ? 'Request access to' : 'Check out'} ${account?.username}@${account?.target?.name}`}</ModalTitle>
      }
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <FormField label="Reason" htmlFor="access-reason" required error={errors.reason?.message}>
          <Controller
            control={control}
            name="reason"
            render={({ field }) => (
              <Input.TextArea {...field} id="access-reason" rows={2} status={errors.reason ? 'error' : undefined} />
            )}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          {needsApproval && (
            <FormField label="Ticket / change ref" htmlFor="access-ticket" error={errors.ticket_ref?.message}>
              <Controller
                control={control}
                name="ticket_ref"
                render={({ field }) => <Input {...field} id="access-ticket" />}
              />
            </FormField>
          )}
          <FormField
            label={`Minutes (max ${account?.max_checkout_minutes ?? ''})`}
            htmlFor="access-minutes"
            error={errors.duration_minutes?.message}
          >
            <Controller
              control={control}
              name="duration_minutes"
              render={({ field }) => (
                <InputNumber
                  {...field}
                  id="access-minutes"
                  className="!w-full"
                  min={1}
                  max={account?.max_checkout_minutes}
                />
              )}
            />
          </FormField>
        </div>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={requesting || checkingOut} onClick={handleSubmit(onSubmit)}>
            {needsApproval ? 'Send request' : 'Check out'}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default RequestAccessModal;
