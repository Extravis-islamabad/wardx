import { Alert, Descriptions, Drawer, InputNumber, Select, Space, Switch, Tabs, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { Button, ErrorState, FormField, ModalFooter, StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { useAccounts, useUpdateAccount } from '@/features/inventory/hooks';
import { SYNC_LABEL, SYNC_VARIANT } from '@/features/rotation/constants';
import { useAccountRotation } from '@/features/rotation/hooks';
import type { Account } from '@/services/inventory-services';
import type { AccountRotation, RotationJob } from '@/services/rotation-services';
import { fmtTime } from '@/utils/format';
import { notify } from '@/utils/notify';
import { ResolveJobModal } from './ResolveJobModal';
import { RotationActionModal, type RotationAction } from './RotationActionModal';
import { RotationJobsTable } from './RotationJobsTable';

const DRAWER_SIZE = 960;

function blockers(r: AccountRotation): string[] {
  const out: string[] = [];
  if (r.non_rotatable_reason) out.push(`This target is ${r.non_rotatable_reason}.`);
  if (!r.rotation_enabled) out.push('Rotation is switched off on this WardX instance (WARDX_ROTATION_ENABLED).');
  if (!r.rotation_allowed) out.push('Rotation is not allowed on this target (edit the target to allow it).');
  if (r.identity_blocker) out.push(r.identity_blocker);
  else if (r.protocol === 'ssh' && !r.host_key_pinned) out.push('The target has no pinned SSH host key (Targets → Learn host key).');
  return out;
}

function RotationStatus({ account, canManage }: { account: Account; canManage: boolean }) {
  const rotation = useAccountRotation(account.id);
  const [action, setAction] = useState<RotationAction | null>(null);
  const [resolving, setResolving] = useState<RotationJob | null>(null);
  const r = rotation.data;
  if (rotation.isError) return <ErrorState error={rotation.error} onRetry={() => void rotation.refetch()} />;
  if (!r) return null;
  const blocked = blockers(r);
  const busy = !!r.open_job;

  return (
    <Space orientation="vertical" size={12} className="w-full">
      {r.risk_flags.includes('high_risk_empty_password') && (
        <Alert type="error" showIcon title="High risk: the stored password is empty. Set a real password or rotate it." />
      )}
      {r.sync_status === 'verify_untrustworthy' && (
        <Alert
          type="error"
          showIcon
          title="Verify untrustworthy: the device accepted a wrong password."
          description="The new password is stored but not verified. Normal check-outs and sessions are blocked until an administrator confirms (accepting the risk) or reconciles it; break-glass still works."
        />
      )}
      {r.sync_status === 'confirmed_untrustworthy' && (
        <Alert
          type="warning"
          showIcon
          title="Confirmed despite a failed negative check (risk accepted)"
          description={`${fmtTime(r.risk_accepted_at)}: ${r.risk_accepted_reason ?? ''}. Listed until a later clean verify.`}
        />
      )}
      {blocked.length > 0 && <Alert type="info" showIcon title="Rotation cannot run here yet" description={blocked.join(' ')} />}
      <Descriptions size="small" bordered column={2}>
        <Descriptions.Item label="Sync">
          <StatusTag label={SYNC_LABEL[r.sync_status] ?? r.sync_status} variant={SYNC_VARIANT[r.sync_status] ?? StatusVariant.NEUTRAL} />
        </Descriptions.Item>
        <Descriptions.Item label="Rotation">{r.rotation_status.replace(/_/g, ' ')}</Descriptions.Item>
        <Descriptions.Item label="Last rotated">
          {fmtTime(r.last_rotated_at)} {r.last_rotation_status ? `(${r.last_rotation_status.replace(/_/g, ' ')})` : ''}
        </Descriptions.Item>
        <Descriptions.Item label="Last verified">
          {fmtTime(r.last_verified_at)} {r.last_verify_method === 'attested' ? '(attested by an admin)' : ''}
        </Descriptions.Item>
        <Descriptions.Item label="Interval">
          {r.effective_interval_days ? `every ${r.effective_interval_days} days` : 'not scheduled'}
        </Descriptions.Item>
        <Descriptions.Item label="After use">{r.effective_rotate_after_use ? 'rotates after every use' : 'no'}</Descriptions.Item>
        <Descriptions.Item label="Password policy" span={2}>
          {r.effective_policy ? (
            <Typography.Text type="secondary" className="text-xs">
              {String(r.effective_policy.length)} characters ({String(r.effective_policy.min_length)}–
              {String(r.effective_policy.max_length)}), symbols {String(r.effective_policy.symbols)}
            </Typography.Text>
          ) : (
            <Typography.Text type="danger">{r.policy_error}</Typography.Text>
          )}
        </Descriptions.Item>
      </Descriptions>
      {canManage && (
        <Space wrap>
          <Button variant="primary" size="small" disabled={busy || blocked.length > 0} onClick={() => setAction('rotate')}>
            Rotate now
          </Button>
          <Button
            variant="admin"
            size="small"
            disabled={busy || blocked.length > 0 || r.sync_status === 'verify_untrustworthy'}
            onClick={() => setAction('verify')}
          >
            Verify now
          </Button>
          <Button
            variant="admin"
            size="small"
            disabled={busy || blocked.length > 0 || !r.reconcile_account_id}
            onClick={() => setAction('reconcile')}
          >
            Reconcile now
          </Button>
          {r.sync_status === 'verify_untrustworthy' && (
            <Button variant="danger" size="small" onClick={() => setAction('confirm')}>
              Confirm (accept risk)
            </Button>
          )}
        </Space>
      )}
      <RotationJobsTable jobs={r.jobs} loading={rotation.isLoading} onResolve={canManage ? setResolving : undefined} />
      <RotationActionModal accountId={account.id} action={action} onClose={() => setAction(null)} />
      <ResolveJobModal job={resolving} onClose={() => setResolving(null)} />
    </Space>
  );
}

function RotationSettings({ account, canManage }: { account: Account; canManage: boolean }) {
  const siblings = useAccounts({ page: 1, page_size: 200, target_id: account.target.id });
  const { mutateAsync: update, isPending } = useUpdateAccount();
  const [afterUse, setAfterUse] = useState(account.rotate_after_use);
  const [interval, setInterval] = useState<number | null>(account.rotation_interval_days);
  const [length, setLength] = useState<number>(account.password_length);
  const [reconcile, setReconcile] = useState<string | null>(account.reconcile_account_id);
  useEffect(() => {
    setAfterUse(account.rotate_after_use);
    setInterval(account.rotation_interval_days);
    setLength(account.password_length);
    setReconcile(account.reconcile_account_id);
  }, [account]);

  const save = async () => {
    try {
      await update({
        id: account.id,
        payload: {
          rotate_after_use: afterUse,
          rotation_interval_days: interval,
          password_length: length,
          reconcile_account_id: reconcile,
        },
      });
      notify.success('Rotation settings saved');
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <>
      <Alert
        className="!mb-3"
        type="info"
        showIcon
        title="Account settings can only make the safe's policy stricter: the shorter interval and the longer password win, and after-use rotation is on if either says so."
      />
      <FormField label="Rotate after every use" htmlFor="rot-after-use">
        <Switch id="rot-after-use" checked={afterUse} disabled={!canManage} onChange={setAfterUse} />
      </FormField>
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
        <FormField label="Rotate every (days)" htmlFor="rot-interval" hint="Blank: the safe's interval">
          <InputNumber id="rot-interval" className="!w-full" min={1} max={3650} disabled={!canManage} value={interval} onChange={(v) => setInterval(v)} />
        </FormField>
        <FormField label="Password length" htmlFor="rot-length" hint="Clamped to the target's maximum">
          <InputNumber id="rot-length" className="!w-full" min={12} max={128} disabled={!canManage} value={length} onChange={(v) => setLength(v ?? 24)} />
        </FormField>
      </div>
      <FormField label="Reconcile account" htmlFor="rot-reconcile" hint="Another account on the same target, e.g. one allowed to run chpasswd through sudo">
        <Select
          id="rot-reconcile"
          allowClear
          className="w-full"
          disabled={!canManage}
          value={reconcile ?? undefined}
          onChange={(v) => setReconcile(v ?? null)}
          loading={siblings.isLoading}
          options={siblings.data?.data?.filter((a) => a.id !== account.id).map((a) => ({ value: a.id, label: a.username }))}
        />
      </FormField>
      {canManage && (
        <ModalFooter>
          <Button variant="primary" size="small" loading={isPending} onClick={save}>
            Save
          </Button>
        </ModalFooter>
      )}
    </>
  );
}

/** An account's Rotation tab: status, history with step timelines, actions and settings. */
export function AccountRotationDrawer({
  account,
  canManage,
  onClose,
}: {
  account: Account | null;
  canManage: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer
      open={!!account}
      size={DRAWER_SIZE}
      title={account ? `${account.username} @ ${account.target.name}` : ''}
      onClose={onClose}
      destroyOnHidden
    >
      {account && (
        <Tabs
          items={[
            { key: 'rotation', label: 'Rotation', children: <RotationStatus account={account} canManage={canManage} /> },
            { key: 'settings', label: 'Rotation settings', children: <RotationSettings account={account} canManage={canManage} /> },
          ]}
        />
      )}
    </Drawer>
  );
}

export default AccountRotationDrawer;
