import { PlusOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { Button, ConfirmModal, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { PICKER_PAGE } from '@/constants/globals';
import { useAuth } from '@/context/AuthContext';
import { useTargets } from '@/features/inventory/hooks';
import { CommandRulesTable, RuleFormModal, RuleTester } from '@/features/sessions/components';
import { useCommandRules, useDeleteCommandRule, useUpdateCommandRule } from '@/features/sessions/hooks';
import type { CommandRule } from '@/services/sessions-services';

export default function CommandPolicy() {
  const { canAccess } = useAuth();
  const canManage = canAccess({ permission: PERMISSIONS.COMMAND_POLICY_MANAGE });
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<CommandRule | null>(null);
  const rules = useCommandRules();
  const targets = useTargets(PICKER_PAGE);
  const { mutateAsync: updateRule } = useUpdateCommandRule();
  const { mutateAsync: deleteRule } = useDeleteCommandRule();
  const targetName = (id: string) => targets.data?.data?.find((t) => t.id === id)?.name ?? 'target';

  return (
    <PageShell
      title="Command policy"
      description="Commands matching a rule are erased on the device before they run. Sessions with rules have arrow keys, history and tab completion turned off so commands cannot slip past."
      actions={
        canManage && (
          <Button variant="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Add rule
          </Button>
        )
      }
    >
      <RuleTester />
      <CommandRulesTable
        query={rules}
        canManage={canManage}
        targetName={targetName}
        onToggle={(rule, is_active) => {
          updateRule({ id: rule.id, payload: { is_active } }).catch(() => {
            // apiClient's interceptor already toasted the failure.
          });
        }}
        onDelete={setDeleting}
      />
      {canManage && <RuleFormModal open={adding} onClose={() => setAdding(false)} />}
      <ConfirmModal
        open={deleting !== null}
        danger
        title="Delete this rule?"
        confirmLabel="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return;
          try {
            await deleteRule(deleting.id);
            setDeleting(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
