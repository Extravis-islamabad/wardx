import { Segmented } from 'antd';
import { useState } from 'react';
import { ConfirmModal, PageShell } from '@/components';
import { CheckoutStatus } from '@/constants/enums/access';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { CheckoutsTable, RevealModal } from '@/features/access/components';
import { CheckoutScope } from '@/features/access/constants';
import { useCheckin, useCheckouts } from '@/features/access/hooks';
import type { Checkout } from '@/services/access-services';
import { notify } from '@/utils/notify';

export default function Checkouts() {
  const { user, canAccess } = useAuth();
  const canSeeAll = canAccess({ permission: PERMISSIONS.CHECKOUTS_VIEW_ALL });
  const canRevoke = canAccess({ permission: PERMISSIONS.CHECKOUTS_REVOKE });
  const [scope, setScope] = useState<CheckoutScope>(CheckoutScope.MINE_ACTIVE);
  const [revealing, setRevealing] = useState<Checkout | null>(null);
  const [checkingIn, setCheckingIn] = useState<Checkout | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const checkouts = useCheckouts({
    page,
    page_size,
    mine: scope === CheckoutScope.MINE_ACTIVE || scope === CheckoutScope.MINE,
    status: scope === CheckoutScope.MINE_ACTIVE || scope === CheckoutScope.ALL_ACTIVE ? CheckoutStatus.ACTIVE : undefined,
  });
  const { mutateAsync: checkin } = useCheckin();

  const scopes = [
    { value: CheckoutScope.MINE_ACTIVE, label: 'My active' },
    { value: CheckoutScope.MINE, label: 'My history' },
    ...(canSeeAll
      ? [
          { value: CheckoutScope.ALL_ACTIVE, label: 'All active' },
          { value: CheckoutScope.ALL, label: 'All' },
        ]
      : []),
  ];
  const checkingInMine = checkingIn?.user?.id === user?.id;

  return (
    <PageShell
      title="Check-outs"
      actions={
        <Segmented
          options={scopes}
          value={scope}
          onChange={(v) => {
            setScope(v as CheckoutScope);
            setPage(1);
          }}
        />
      }
    >
      <CheckoutsTable
        query={checkouts}
        pagination={paginationFor(checkouts.data?.total)}
        currentUserId={user?.id}
        canRevoke={canRevoke}
        onReveal={setRevealing}
        onCheckin={setCheckingIn}
      />
      <RevealModal checkout={revealing} onClose={() => setRevealing(null)} />
      <ConfirmModal
        open={checkingIn !== null}
        danger={!checkingInMine}
        title={checkingInMine ? 'Check this credential back in?' : 'Revoke this check-out?'}
        confirmLabel={checkingInMine ? 'Check in' : 'Revoke'}
        onCancel={() => setCheckingIn(null)}
        onConfirm={async () => {
          if (!checkingIn) return;
          try {
            await checkin(checkingIn.id);
            notify.success('Checked in');
            setCheckingIn(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
