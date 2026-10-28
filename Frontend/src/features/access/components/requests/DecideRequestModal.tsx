import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle, Text } from '@/components';
import { useDecideRequest } from '@/features/access/hooks';
import {
  decisionFormDefaults,
  decisionFormSchema,
  type DecisionFormValues,
} from '@/features/access/schemas/decisionSchema';
import type { AccessRequest } from '@/services/access-services';
import { notify } from '@/utils/notify';

export interface PendingDecision {
  request: AccessRequest;
  approve: boolean;
}

export function DecideRequestModal({ decision, onClose }: { decision: PendingDecision | null; onClose: () => void }) {
  const { mutateAsync: decide, isPending } = useDecideRequest();
  const { control, handleSubmit, reset } = useForm<DecisionFormValues>({
    resolver: zodResolver(decisionFormSchema),
    defaultValues: decisionFormDefaults,
  });

  useEffect(() => {
    if (decision) reset(decisionFormDefaults);
  }, [decision, reset]);

  const onSubmit = async (values: DecisionFormValues) => {
    if (!decision) return;
    try {
      await decide({
        id: decision.request.id,
        payload: { approve: decision.approve, note: values.note || undefined },
      });
      notify.success(decision.approve ? 'Approved' : 'Denied');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const request = decision?.request;
  return (
    <Modal
      open={!!decision}
      title={<ModalTitle>{decision?.approve ? 'Approve request' : 'Deny request'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        {request && (
          <Text className="mb-3">
            <b>{request.requester?.username}</b> wants{' '}
            <b>
              {request.account?.username}@{request.account?.target_name}
            </b>{' '}
            for {request.duration_minutes} minutes: “{request.reason}”.
          </Text>
        )}
        <FormField label="Note" htmlFor="decision-note">
          <Controller
            control={control}
            name="note"
            render={({ field }) => <Input.TextArea {...field} id="decision-note" rows={2} placeholder="Note (optional)" />}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={decision?.approve ? 'primary' : 'danger'}
            size="small"
            loading={isPending}
            onClick={handleSubmit(onSubmit)}
          >
            {decision?.approve ? 'Approve' : 'Deny'}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default DecideRequestModal;
