import { PlusOutlined } from '@ant-design/icons';
import { Alert, Input } from 'antd';
import { useState } from 'react';
import { Button, PageShell } from '@/components';
import { usePagination } from '@/hooks';
import { AppDetailDrawer, AppFormModal, AppsTable, SecretOnceModal } from '@/features/provider/components';
import { useApps, useUpdateApp } from '@/features/provider/hooks';
import type { AppIdentity, NewAppSecret } from '@/services/provider-services';
import { notify } from '@/utils/notify';

/** Application identities: the non-human clients (MonetX, its collectors) of the credential provider. */
export default function AppIdentities() {
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<AppIdentity | null>(null);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [created, setCreated] = useState<NewAppSecret | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const apps = useApps({ page, page_size, search: search || undefined });
  const { mutateAsync: updateApp } = useUpdateApp();
  // The drawer reads the live row, so added or revoked secrets show at once.
  const open = apps.data?.data?.find((a) => a.id === openId) ?? null;

  const toggle = (app: AppIdentity, enabled: boolean) => {
    updateApp({ id: app.id, payload: { enabled } })
      .then(() => notify.success(enabled ? 'Enabled' : 'Disabled: its tokens stopped working at once'))
      .catch(() => {
        // apiClient's interceptor already toasted the failure.
      });
  };

  return (
    <PageShell
      title="Application identities"
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Search"
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          <Button variant="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            Add application
          </Button>
        </>
      }
    >
      <Alert
        className="!mb-3"
        type="info"
        showIcon
        title="Applications such as MonetX fetch device credentials at poll time with a client secret. They never sign in to the console or the gateway; give one access by adding it to a safe with 'fetch'."
      />
      <AppsTable
        query={apps}
        pagination={paginationFor(apps.data?.total)}
        onEdit={setEditing}
        onOpen={(a) => setOpenId(a.id)}
        onToggleEnabled={toggle}
      />
      <AppFormModal
        open={creating || editing !== null}
        app={editing}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onCreated={setCreated}
      />
      <AppDetailDrawer app={open} onClose={() => setOpenId(null)} onSecretCreated={setCreated} />
      <SecretOnceModal created={created} onClose={() => setCreated(null)} />
    </PageShell>
  );
}
