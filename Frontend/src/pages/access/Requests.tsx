import { Segmented } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { ROUTES } from '@/constants/enums/routes';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { DecideRequestModal, RequestsTable, type PendingDecision } from '@/features/access/components';
import { RequestScope } from '@/features/access/constants';
import { useCancelRequest, useCreateCheckout, useRequests } from '@/features/access/hooks';
import type { AccessRequest } from '@/services/access-services';
import { notify } from '@/utils/notify';

export default function Requests() {
  const { user, canAccess } = useAuth();
  // Who decides is per safe and level, so every user has a queue (often empty); role
  // approvers start on it.
  const startOnQueue = canAccess({ permission: PERMISSIONS.REQUESTS_DECIDE });
  const navigate = useNavigate();
  const [scope, setScope] = useState<RequestScope>(startOnQueue ? RequestScope.QUEUE : RequestScope.MINE);
  const [deciding, setDeciding] = useState<PendingDecision | null>(null);
  const [checkingOutId, setCheckingOutId] = useState<string | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const requests = useRequests({
    page,
    page_size,
    mine: scope === RequestScope.MINE,
    queue: scope === RequestScope.QUEUE,
  });
  const { mutateAsync: cancelRequest } = useCancelRequest();
  const { mutateAsync: createCheckout } = useCreateCheckout();

  const onCheckout = async (r: AccessRequest) => {
    setCheckingOutId(r.id);
    try {
      await createCheckout({ account_id: r.account.id, request_id: r.id });
      notify.success('Checked out — reveal it from Check-outs');
      navigate(ROUTES.CHECKOUTS);
    } catch {
      // apiClient's interceptor already toasted the failure.
    } finally {
      setCheckingOutId(null);
    }
  };

  const onCancel = async (r: AccessRequest) => {
    try {
      await cancelRequest(r.id);
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const scopes = [
    { value: RequestScope.QUEUE, label: 'Awaiting my decision' },
    { value: RequestScope.MINE, label: 'My requests' },
    { value: RequestScope.ALL, label: 'All I can see' },
  ];

  return (
    <PageShell
      title="Access requests"
      actions={
        <Segmented
          options={scopes}
          value={scope}
          onChange={(v) => {
            setScope(v as RequestScope);
            setPage(1);
          }}
        />
      }
    >
      <RequestsTable
        query={requests}
        pagination={paginationFor(requests.data?.total)}
        currentUserId={user?.id}
        canDecide={scope === RequestScope.QUEUE}
        checkingOutId={checkingOutId}
        onDecide={(request, approve) => setDeciding({ request, approve })}
        onCheckout={(r) => void onCheckout(r)}
        onCancel={(r) => void onCancel(r)}
      />
      <DecideRequestModal decision={deciding} onClose={() => setDeciding(null)} />
    </PageShell>
  );
}
