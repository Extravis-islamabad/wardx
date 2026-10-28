import { zodResolver } from '@hookform/resolvers/zod';
import { Input, Modal, Select } from 'antd';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { PLATFORMS } from '@/constants/enums/inventory';
import { PICKER_PAGE } from '@/constants/globals';
import { useTargets } from '@/features/inventory/hooks';
import { RULE_SCOPE_OPTIONS, RuleScope } from '@/features/sessions/constants';
import { useCreateCommandRule } from '@/features/sessions/hooks';
import {
  commandRuleFormDefaults,
  commandRuleFormSchema,
  type CommandRuleFormValues,
} from '@/features/sessions/schemas/commandRuleSchema';
import { notify } from '@/utils/notify';

export function RuleFormModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { mutateAsync: createRule, isPending } = useCreateCommandRule();
  const {
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<CommandRuleFormValues>({
    resolver: zodResolver(commandRuleFormSchema),
    defaultValues: commandRuleFormDefaults,
  });
  const scope = watch('scope');
  const targets = useTargets(PICKER_PAGE, { enabled: open && scope === RuleScope.TARGET });

  useEffect(() => {
    if (open) reset(commandRuleFormDefaults);
  }, [open, reset]);

  const onSubmit = async (values: CommandRuleFormValues) => {
    try {
      await createRule({
        pattern: values.pattern,
        description: values.description || undefined,
        platform: values.scope === RuleScope.PLATFORM ? values.platform : undefined,
        target_id: values.scope === RuleScope.TARGET ? values.target_id : undefined,
      });
      notify.success('Rule added; it applies to sessions that start from now');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal open={open} title={<ModalTitle>Add deny rule</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        <FormField
          label="Pattern (regular expression, case-insensitive)"
          htmlFor="rule-pattern"
          required
          hint="Matched against the typed command with spaces collapsed, e.g. ^(reload|write erase)\b"
          error={errors.pattern?.message}
        >
          <Controller
            control={control}
            name="pattern"
            render={({ field }) => (
              <Input {...field} id="rule-pattern" className="font-mono" status={errors.pattern ? 'error' : undefined} />
            )}
          />
        </FormField>
        <FormField label="Shown to the user when blocked" htmlFor="rule-description" error={errors.description?.message}>
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input {...field} id="rule-description" />}
          />
        </FormField>
        <FormField label="Applies to" htmlFor="rule-scope">
          <Controller
            control={control}
            name="scope"
            render={({ field }) => <Select {...field} id="rule-scope" className="w-full" options={RULE_SCOPE_OPTIONS} />}
          />
        </FormField>
        {scope === RuleScope.PLATFORM && (
          <FormField label="Platform" htmlFor="rule-platform">
            <Controller
              control={control}
              name="platform"
              render={({ field }) => (
                <Select {...field} id="rule-platform" className="w-full" options={PLATFORMS} showSearch optionFilterProp="label" />
              )}
            />
          </FormField>
        )}
        {scope === RuleScope.TARGET && (
          <FormField label="Target" htmlFor="rule-target">
            <Controller
              control={control}
              name="target_id"
              render={({ field }) => (
                <Select
                  {...field}
                  id="rule-target"
                  className="w-full"
                  showSearch
                  optionFilterProp="label"
                  loading={targets.isLoading}
                  options={targets.data?.data?.map((t) => ({ value: t.id, label: `${t.name} (${t.address})` }))}
                />
              )}
            />
          </FormField>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
            Add rule
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default RuleFormModal;
