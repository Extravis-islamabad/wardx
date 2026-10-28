import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Input, InputNumber, Select, Switch } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Button, FormField, ModalFooter } from '@/components';
import { TICKET_MODE_OPTIONS, TicketMode } from '@/constants/enums/safes';
import { useSafeMembers, useSafePolicy, useSaveSafePolicy } from '@/features/safes/hooks';
import { policyFormSchema, policyFormValuesFrom, type PolicyFormValues } from '@/features/safes/schemas/policySchema';
import type { Safe } from '@/services/safes-services';
import { notify } from '@/utils/notify';
import { ApprovalLevelsField } from './ApprovalLevelsField';

/** The safe's approval policy. Editable with safes.manage; read-only otherwise. */
export function ApprovalPolicyTab({ safe, canEdit }: { safe: Safe; canEdit: boolean }) {
  const policy = useSafePolicy(safe.id);
  // Named approvers are picked from the members; only editors (safes.manage) load them.
  const members = useSafeMembers(canEdit ? safe.id : undefined);
  const { mutateAsync: save, isPending } = useSaveSafePolicy(safe.id);
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PolicyFormValues>({
    resolver: zodResolver(policyFormSchema),
    defaultValues: policyFormValuesFrom(policy.data),
  });
  const required = useWatch({ control, name: 'approval_required' });
  const ticketMode = useWatch({ control, name: 'ticket_mode' });

  useEffect(() => {
    if (policy.data) reset(policyFormValuesFrom(policy.data));
  }, [policy.data, reset]);

  const onSubmit = async (values: PolicyFormValues) => {
    try {
      await save({ ...values, ticket_pattern: values.ticket_pattern || null });
      notify.success('Approval policy saved');
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const readOnly = !canEdit;
  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <Alert
        className="!mb-3"
        type="info"
        showIcon
        title="Requests run on the policy as it was when they were made; changes apply to new requests."
      />
      <FormField label="Approval required" htmlFor="policy-required">
        <Controller
          control={control}
          name="approval_required"
          render={({ field }) => (
            <Switch id="policy-required" checked={field.value} onChange={field.onChange} disabled={readOnly} />
          )}
        />
      </FormField>
      {required && (
        <>
          <FormField label="Approval levels (in order)" htmlFor="policy-levels">
            <ApprovalLevelsField
              control={control}
              errors={errors}
              members={members.data ?? []}
              readOnly={readOnly}
              knownNames={Object.fromEntries(
                (policy.data?.levels ?? [])
                  .filter((l) => l.approver_key && l.approver_name)
                  .map((l) => [l.approver_key as string, l.approver_name as string]),
              )}
            />
          </FormField>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <FormField
              label="Approval window (minutes)"
              htmlFor="policy-window"
              hint="From the last approval; then a new request is needed."
              error={errors.approval_window_minutes?.message}
            >
              <Controller
                control={control}
                name="approval_window_minutes"
                render={({ field }) => (
                  <InputNumber {...field} id="policy-window" min={1} max={10080} disabled={readOnly} className="!w-full" />
                )}
              />
            </FormField>
            <FormField
              label="Level timeout (hours)"
              htmlFor="policy-timeout"
              hint="An undecided level expires the request."
              error={errors.level_timeout_hours?.message}
            >
              <Controller
                control={control}
                name="level_timeout_hours"
                render={({ field }) => (
                  <InputNumber {...field} id="policy-timeout" min={1} max={720} disabled={readOnly} className="!w-full" />
                )}
              />
            </FormField>
            <FormField
              label="Multi-use"
              htmlFor="policy-multi"
              hint="Off: one check-out or gateway session per approval."
            >
              <Controller
                control={control}
                name="approval_multi_use"
                render={({ field }) => (
                  <Switch id="policy-multi" checked={field.value} onChange={field.onChange} disabled={readOnly} />
                )}
              />
            </FormField>
          </div>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <FormField label="Ticket number" htmlFor="policy-ticket-mode">
              <Controller
                control={control}
                name="ticket_mode"
                render={({ field }) => (
                  <Select {...field} id="policy-ticket-mode" options={TICKET_MODE_OPTIONS} disabled={readOnly} />
                )}
              />
            </FormField>
            {ticketMode !== TicketMode.OFF && (
              <div className="md:col-span-2">
                <FormField
                  label="Ticket pattern (regular expression, optional)"
                  htmlFor="policy-ticket-pattern"
                  hint="Must match the whole ticket, e.g. CHG-\d{6}. Nested quantifiers and backreferences are refused."
                  error={errors.ticket_pattern?.message}
                >
                  <Controller
                    control={control}
                    name="ticket_pattern"
                    render={({ field }) => (
                      <Input {...field} id="policy-ticket-pattern" className="font-mono" disabled={readOnly} />
                    )}
                  />
                </FormField>
              </div>
            )}
          </div>
        </>
      )}
      {canEdit && (
        <ModalFooter>
          <Button variant="primary" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
            Save policy
          </Button>
        </ModalFooter>
      )}
    </form>
  );
}

export default ApprovalPolicyTab;
