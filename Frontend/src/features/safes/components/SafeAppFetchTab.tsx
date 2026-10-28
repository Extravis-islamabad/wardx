import { Alert, InputNumber, Switch } from 'antd';
import { useEffect, useState } from 'react';
import { Button, FormField, ModalFooter } from '@/components';
import { useSafeAppFetch, useSaveSafeAppFetch } from '@/features/safes/hooks';
import type { SafeAppFetch } from '@/services/safes-services';
import { notify } from '@/utils/notify';

const DEFAULTS: SafeAppFetch = { allow_app_fetch: false, app_cache_seconds: 300 };

/** Credential provider settings: app fetches from approval-required safes, and the cache time. */
export function SafeAppFetchTab({ safeId, canEdit }: { safeId: string; canEdit: boolean }) {
  const settings = useSafeAppFetch(safeId);
  const { mutateAsync: save, isPending } = useSaveSafeAppFetch(safeId);
  const [form, setForm] = useState<SafeAppFetch>(DEFAULTS);
  useEffect(() => {
    if (settings.data) setForm({ ...DEFAULTS, ...settings.data });
  }, [settings.data]);
  const ro = !canEdit;

  const submit = async () => {
    try {
      await save({ allow_app_fetch: form.allow_app_fetch, app_cache_seconds: form.app_cache_seconds });
      notify.success('Application access saved');
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
        title="Applications (MonetX) fetch credentials only from safes where they are a member with 'fetch'. A fetch is audited but is not a check-out."
      />
      {settings.data?.approval_required && !form.allow_app_fetch && (
        <Alert
          className="!mb-3"
          type="warning"
          showIcon
          title="This safe requires approval, so application fetches are refused until you allow them here."
        />
      )}
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
        <FormField
          label="Allow app fetches despite approval"
          htmlFor="saf-allow"
          hint="Only matters when the safe requires approval for people"
        >
          <Switch
            id="saf-allow"
            checked={form.allow_app_fetch}
            disabled={ro}
            onChange={(v) => setForm((f) => ({ ...f, allow_app_fetch: v }))}
          />
        </FormField>
        <FormField
          label="Apps may cache for (seconds)"
          htmlFor="saf-cache"
          hint="0 to 3600; sent to apps as max_cache_seconds"
        >
          <InputNumber
            id="saf-cache"
            className="!w-full"
            min={0}
            max={3600}
            disabled={ro}
            value={form.app_cache_seconds}
            onChange={(v) => setForm((f) => ({ ...f, app_cache_seconds: v ?? 300 }))}
          />
        </FormField>
      </div>
      {canEdit && (
        <ModalFooter>
          <Button variant="primary" size="small" loading={isPending} onClick={() => void submit()}>
            Save
          </Button>
        </ModalFooter>
      )}
    </>
  );
}

export default SafeAppFetchTab;
