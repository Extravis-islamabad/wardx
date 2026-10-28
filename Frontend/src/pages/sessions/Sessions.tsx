import { Input, Segmented, Typography } from 'antd';
import { useState } from 'react';
import { ConfirmModal, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { SessionStatus } from '@/constants/enums/sessions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { SessionDrawer, SessionsTable } from '@/features/sessions/components';
import { SessionScope } from '@/features/sessions/constants';
import { useGatewayInfo, useSessions, useTerminateSession } from '@/features/sessions/hooks';
import type { GatewaySession } from '@/services/sessions-services';
import { notify } from '@/utils/notify';

export default function Sessions() {
  const { canAccess } = useAuth();
  const canSeeAll = canAccess({ permission: PERMISSIONS.SESSIONS_VIEW_ALL });
  const canTerminate = canAccess({ permission: PERMISSIONS.SESSIONS_TERMINATE });
  const [scope, setScope] = useState<SessionScope>(canSeeAll ? SessionScope.ALL : SessionScope.MINE);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<GatewaySession | null>(null);
  const [killing, setKilling] = useState<GatewaySession | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const sessions = useSessions({
    page,
    page_size,
    status: scope === SessionScope.ACTIVE ? SessionStatus.ACTIVE : undefined,
    mine: scope === SessionScope.MINE,
    search: search || undefined,
  });
  const gateway = useGatewayInfo();
  const { mutateAsync: terminate } = useTerminateSession();

  return (
    <PageShell
      title="Sessions"
      description={
        gateway.data && (
          <>
            Connect:{' '}
            <Typography.Text code copyable>
              {`ssh -p ${gateway.data.port} ${gateway.data.login_format}@${gateway.data.host}`}
            </Typography.Text>
          </>
        )
      }
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Target or account"
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          <Segmented
            value={scope}
            onChange={(v) => {
              setScope(v as SessionScope);
              setPage(1);
            }}
            options={[
              ...(canSeeAll
                ? [
                    { value: SessionScope.ALL, label: 'All' },
                    { value: SessionScope.ACTIVE, label: 'Live' },
                  ]
                : []),
              { value: SessionScope.MINE, label: 'Mine' },
            ]}
          />
        </>
      }
    >
      <SessionsTable
        query={sessions}
        pagination={paginationFor(sessions.data?.total)}
        canTerminate={canTerminate}
        onOpen={setOpen}
        onTerminate={setKilling}
      />
      <SessionDrawer session={open} onClose={() => setOpen(null)} />
      <ConfirmModal
        open={killing !== null}
        danger
        title="Disconnect this session now?"
        confirmLabel="Kill"
        onCancel={() => setKilling(null)}
        onConfirm={async () => {
          if (!killing) return;
          try {
            const r = await terminate(killing.id);
            notify.success(r?.message ?? 'Termination requested');
            setKilling(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
