import { Alert, Card, Space, Tooltip, Typography } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, StatusTag } from '@/components';
import { SyncStatus } from '@/constants/enums/identity';
import { StatusVariant } from '@/constants/enums/status';
import { SYNC_STATUS_VARIANT } from '@/features/identity/constants';
import { useRunDirectorySync } from '@/features/identity/hooks';
import type { DirectoryConfig, SyncResult } from '@/services/identity-services';
import { fromNow } from '@/utils/format';

export function DirectorySyncPanel({ config }: { config: DirectoryConfig }) {
  const run = useRunDirectorySync();
  const [shown, setShown] = useState<SyncResult | null>(null);
  const [confirmingForce, setConfirmingForce] = useState(false);
  const r = shown ?? config?.last_sync_summary;

  const runSync = async (dryRun: boolean, force?: boolean) => {
    try {
      setShown(await run.mutateAsync({ dryRun, force }));
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Card
      size="small"
      className="!mt-4"
      title="Directory sync"
      extra={
        <Space>
          <Button variant="admin" size="small" loading={run.isPending} disabled={!config?.enabled} onClick={() => void runSync(true)}>
            Preview
          </Button>
          <Button variant="primary" size="small" loading={run.isPending} disabled={!config?.enabled} onClick={() => void runSync(false)}>
            Run now
          </Button>
        </Space>
      }
    >
      <Typography.Text type="secondary">
        {config?.sync_interval_minutes ? `Every ${config.sync_interval_minutes} min` : 'Schedule off'} · last run{' '}
        {config?.last_sync_at ? fromNow(config.last_sync_at) : 'never'}
      </Typography.Text>
      {r && (
        <div className="mt-3 space-y-2">
          <Space wrap>
            <StatusTag label={r.dry_run ? `preview: ${r.status}` : r.status} variant={SYNC_STATUS_VARIANT[r.status]} />
            <span>{r.checked} checked</span>
          </Space>
          {r.disabled?.length > 0 && (
            <Space size={4} wrap>
              <b>{r.dry_run || r.status !== SyncStatus.OK ? 'Would disable' : 'Disabled'}:</b>
              {r.disabled.map((d) => (
                <Tooltip key={d.username} title={d.reason}>
                  <StatusTag label={d.username} variant={StatusVariant.DANGER} />
                </Tooltip>
              ))}
            </Space>
          )}
          {r.enabled?.length > 0 && (
            <Space size={4} wrap>
              <b>Re-enabled:</b>
              {r.enabled.map((u) => (
                <StatusTag key={u} label={u} variant={StatusVariant.SUCCESS} />
              ))}
            </Space>
          )}
          {r.role_changes?.length > 0 && (
            <Space size={4} wrap>
              <b>Role changes:</b>
              {r.role_changes.map((c) => (
                <StatusTag key={c.username} label={`${c.username}: ${c.from} → ${c.to}`} variant={StatusVariant.OUTLINE} />
              ))}
            </Space>
          )}
          {(r.revoked_checkouts > 0 || r.killed_sessions > 0) && (
            <div>
              Revoked {r.revoked_checkouts} check-out(s), ended {r.killed_sessions} live session(s).
            </div>
          )}
          {r.problems?.map((p) => (
            <Alert key={p} type={r.status === SyncStatus.OK ? 'info' : 'warning'} showIcon title={p} />
          ))}
          {r.status === SyncStatus.NEEDS_REVIEW && !r.dry_run && (
            <Button variant="danger" size="small" onClick={() => setConfirmingForce(true)}>
              Apply anyway
            </Button>
          )}
        </div>
      )}
      <ConfirmModal
        open={confirmingForce}
        danger
        title={`Disable ${r?.disabled?.length ?? 0} users?`}
        description="Only if you have checked the list and these people really left."
        confirmLabel="Apply anyway"
        onCancel={() => setConfirmingForce(false)}
        onConfirm={async () => {
          await runSync(false, true);
          setConfirmingForce(false);
        }}
      />
    </Card>
  );
}

export default DirectorySyncPanel;
