import { Alert, Checkbox, InputNumber, Switch } from 'antd';
import { useEffect, useState } from 'react';
import { Button, FormField, ModalFooter } from '@/components';
import { WEEKDAYS } from '@/features/rotation/constants';
import { useSafeRotationPolicy, useSaveSafeRotationPolicy } from '@/features/rotation/hooks';
import type { SafeRotationPolicy } from '@/services/rotation-services';
import { notify } from '@/utils/notify';

const DEFAULTS: SafeRotationPolicy = {
  rotate_after_use: false,
  rotation_interval_days: null,
  verify_interval_hours: 24,
  auto_reconcile: false,
  maintenance_window: null,
  max_release_wait_minutes: 240,
};

/** The safe's rotation policy. Editable with safes.manage; read-only otherwise. */
export function SafeRotationPolicyTab({ safeId, canEdit }: { safeId: string; canEdit: boolean }) {
  const policy = useSafeRotationPolicy(safeId);
  const { mutateAsync: save, isPending } = useSaveSafeRotationPolicy(safeId);
  const [form, setForm] = useState<SafeRotationPolicy>(DEFAULTS);
  useEffect(() => {
    if (policy.data) setForm({ ...DEFAULTS, ...policy.data });
  }, [policy.data]);
  const set = (patch: Partial<SafeRotationPolicy>) => setForm((f) => ({ ...f, ...patch }));
  const window = form.maintenance_window;
  const ro = !canEdit;

  const submit = async () => {
    try {
      const { safe_id: _ignored, ...body } = form;
      await save(body);
      notify.success('Rotation policy saved');
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
        title="Nothing rotates unless rotation is switched on for WardX and allowed on the target. A rotation never runs while anyone holds the account."
      />
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
        <FormField label="Rotate after use" htmlFor="srp-after-use" hint="After every check-in, expiry, revoke or session end, once every holder released it">
          <Switch id="srp-after-use" checked={form.rotate_after_use} disabled={ro} onChange={(v) => set({ rotate_after_use: v })} />
        </FormField>
        <FormField label="Auto-reconcile when out of sync" htmlFor="srp-auto" hint="Still alerts; needs a reconcile account">
          <Switch id="srp-auto" checked={form.auto_reconcile} disabled={ro} onChange={(v) => set({ auto_reconcile: v })} />
        </FormField>
        <FormField label="Rotate every (days)" htmlFor="srp-interval" hint="Blank: no scheduled rotation">
          <InputNumber id="srp-interval" className="!w-full" min={1} max={3650} disabled={ro} value={form.rotation_interval_days} onChange={(v) => set({ rotation_interval_days: v })} />
        </FormField>
        <FormField label="Verify every (hours)" htmlFor="srp-verify">
          <InputNumber id="srp-verify" className="!w-full" min={1} max={8760} disabled={ro} value={form.verify_interval_hours} onChange={(v) => set({ verify_interval_hours: v ?? 24 })} />
        </FormField>
        <FormField label="Alert when a wait for release passes (minutes)" htmlFor="srp-wait" hint="It keeps waiting; it never rotates under a holder">
          <InputNumber id="srp-wait" className="!w-full" min={5} max={10080} disabled={ro} value={form.max_release_wait_minutes} onChange={(v) => set({ max_release_wait_minutes: v ?? 240 })} />
        </FormField>
      </div>
      <FormField label="Maintenance window for scheduled rotation (UTC)" htmlFor="srp-window" hint="Off: any time. On-demand and after-use rotations ignore it.">
        <Switch
          id="srp-window"
          checked={!!window}
          disabled={ro}
          onChange={(on) => set({ maintenance_window: on ? { days: [5, 6], start_hour: 1, end_hour: 5 } : null })}
        />
      </FormField>
      {window && (
        <div className="flex flex-wrap items-center gap-3 pb-3">
          <Checkbox.Group
            disabled={ro}
            value={window.days}
            onChange={(days) => set({ maintenance_window: { ...window, days: days as number[] } })}
            options={WEEKDAYS.map((d, i) => ({ value: i, label: d }))}
          />
          <span>from</span>
          <InputNumber aria-label="Start hour" min={0} max={23} disabled={ro} value={window.start_hour} onChange={(v) => set({ maintenance_window: { ...window, start_hour: v ?? 0 } })} />
          <span>to</span>
          <InputNumber aria-label="End hour" min={1} max={24} disabled={ro} value={window.end_hour} onChange={(v) => set({ maintenance_window: { ...window, end_hour: v ?? 24 } })} />
        </div>
      )}
      {canEdit && (
        <ModalFooter>
          <Button variant="primary" size="small" loading={isPending} onClick={submit}>
            Save
          </Button>
        </ModalFooter>
      )}
    </>
  );
}

export default SafeRotationPolicyTab;
