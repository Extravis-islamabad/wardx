import { PlusOutlined } from '@ant-design/icons';
import { Alert, DatePicker, Drawer, Space, Tabs, type TableProps } from 'antd';
import type { Dayjs } from 'dayjs';
import { useState } from 'react';
import { Button, ConfirmModal, DataTable, StatusTag } from '@/components';
import { STATUS_VARIANT, StatusVariant } from '@/constants/enums/status';
import { useAddAppSecret, useAppFetches, useRevokeAppSecret } from '@/features/provider/hooks';
import { tableStateProps } from '@/lib/tableStateProps';
import type { AppFetchEvent, AppIdentity, AppSecret, NewAppSecret } from '@/services/provider-services';
import { fmtTime } from '@/utils/format';
import { notify } from '@/utils/notify';

const DRAWER_SIZE = 900;
const FETCH_PAGE = { page: 1, page_size: 50 } as const;
const SECRET_VARIANT: Record<AppSecret['status'], StatusVariant> = {
  active: StatusVariant.SUCCESS,
  expired: StatusVariant.WARNING,
  revoked: StatusVariant.NEUTRAL,
};

interface AppDetailDrawerProps {
  app: AppIdentity | null;
  onClose: () => void;
  onSecretCreated: (created: NewAppSecret) => void;
}

/** An app's client secrets (add, shown once; revoke) and its recent fetches from the audit trail. */
export function AppDetailDrawer({ app, onClose, onSecretCreated }: AppDetailDrawerProps) {
  const [expiresAt, setExpiresAt] = useState<Dayjs | null>(null);
  const [revoking, setRevoking] = useState<AppSecret | null>(null);
  const { mutateAsync: addSecret, isPending: adding } = useAddAppSecret();
  const { mutateAsync: revokeSecret } = useRevokeAppSecret();
  const fetches = useAppFetches(app?.id, FETCH_PAGE);
  const unrevoked = app?.secrets.filter((s) => s.status !== 'revoked').length ?? 0;

  const add = async () => {
    if (!app) return;
    try {
      onSecretCreated(await addSecret({ id: app.id, expiresAt: expiresAt?.toISOString() ?? null }));
      setExpiresAt(null);
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const secretColumns: TableProps<AppSecret>['columns'] = [
    { title: 'Slot', dataIndex: 'slot', key: 'slot', width: 60 },
    { title: 'Prefix', key: 'prefix', render: (_, s) => <code>{s?.prefix}…</code> },
    {
      title: 'Status',
      key: 'status',
      render: (_, s) => <StatusTag label={s?.status} variant={SECRET_VARIANT[s?.status]} />,
    },
    { title: 'Created', key: 'created', render: (_, s) => fmtTime(s?.created_at) },
    { title: 'Expires', key: 'expires', render: (_, s) => fmtTime(s?.expires_at) },
    { title: 'Last used', key: 'used', render: (_, s) => fmtTime(s?.last_used_at) },
    {
      title: '',
      key: 'actions',
      width: 90,
      render: (_, s) =>
        s?.status !== 'revoked' && (
          <Button variant="danger" size="small" onClick={() => setRevoking(s)}>
            Revoke
          </Button>
        ),
    },
  ];

  const fetchColumns: TableProps<AppFetchEvent>['columns'] = [
    { title: 'When', key: 'when', render: (_, e) => fmtTime(e?.occurred_at) },
    {
      title: 'Outcome',
      key: 'outcome',
      render: (_, e) => (
        <StatusTag label={e?.error_code ?? e?.outcome} variant={STATUS_VARIANT[e?.outcome] ?? StatusVariant.NEUTRAL} />
      ),
    },
    { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (v: string | null) => v ?? '—' },
    { title: 'Purpose', dataIndex: 'purpose', key: 'purpose', render: (v: string | null) => v ?? '—' },
    { title: 'Username', dataIndex: 'username', key: 'username', render: (v: string | null) => v ?? '—' },
    { title: 'Source', dataIndex: 'source_ip', key: 'source_ip', render: (v: string | null) => v ?? '—' },
    { title: 'Version', dataIndex: 'version_id', key: 'version', render: (v: string | null) => (v ? <code>{v.slice(0, 11)}</code> : '—') },
  ];

  return (
    <Drawer open={!!app} onClose={onClose} size={DRAWER_SIZE} title={app?.name} destroyOnHidden>
      {app && (
        <Tabs
          items={[
            {
              key: 'secrets',
              label: 'Client secrets',
              children: (
                <>
                  <Alert
                    className="!mb-3"
                    type="info"
                    showIcon
                    title="At most two active secrets. To rotate: add a second, move the collectors to it, then revoke the first."
                  />
                  <Space className="mb-3 flex justify-end">
                    <DatePicker
                      showTime
                      placeholder="Expires (optional)"
                      value={expiresAt}
                      onChange={setExpiresAt}
                      aria-label="Secret expiry"
                    />
                    <Button
                      variant="primary"
                      size="small"
                      icon={<PlusOutlined />}
                      loading={adding}
                      disabled={unrevoked >= 2}
                      onClick={() => void add()}
                    >
                      Add secret
                    </Button>
                  </Space>
                  <DataTable<AppSecret> rowKey="id" dataSource={app.secrets} pagination={false} columns={secretColumns} />
                </>
              ),
            },
            {
              key: 'fetches',
              label: 'Recent fetches',
              children: (
                <DataTable<AppFetchEvent>
                  rowKey={(e) => `${e.occurred_at}-${e.version_id ?? e.error_code}`}
                  {...tableStateProps(fetches, "Couldn't load fetches")}
                  dataSource={fetches.data?.data}
                  pagination={false}
                  columns={fetchColumns}
                />
              ),
            },
          ]}
        />
      )}
      <ConfirmModal
        open={revoking !== null}
        danger
        title={`Revoke secret ${revoking?.prefix ?? ''}…?`}
        description="Takes effect at once: tokens issued for it stop working. Collectors still using it lose access."
        confirmLabel="Revoke"
        onCancel={() => setRevoking(null)}
        onConfirm={async () => {
          if (!app || !revoking) return;
          try {
            await revokeSecret({ id: app.id, secretId: revoking.id });
            notify.success('Secret revoked');
            setRevoking(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </Drawer>
  );
}

export default AppDetailDrawer;
