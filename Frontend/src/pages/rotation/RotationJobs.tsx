import { Select } from 'antd';
import { useState } from 'react';
import { ErrorState, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { JOB_STATUS_OPTIONS, REASON_LABEL } from '@/features/rotation/constants';
import { ResolveJobModal, RotationAttentionPanel, RotationJobsTable } from '@/features/rotation/components';
import { useRotationJobs } from '@/features/rotation/hooks';
import type { RotationJob } from '@/services/rotation-services';

export default function RotationJobs() {
  const { canAccess } = useAuth();
  const canManage = canAccess({ permission: PERMISSIONS.ACCOUNTS_MANAGE });
  const [status, setStatus] = useState<string | undefined>();
  const [reason, setReason] = useState<string | undefined>();
  const [resolving, setResolving] = useState<RotationJob | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const jobs = useRotationJobs({ page, page_size, status, reason });

  return (
    <PageShell
      title="Password rotation"
      actions={
        <>
          <Select
            allowClear
            className="min-w-44"
            placeholder="Any status"
            aria-label="Status"
            value={status}
            options={JOB_STATUS_OPTIONS}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <Select
            allowClear
            className="min-w-40"
            placeholder="Any trigger"
            aria-label="Trigger"
            value={reason}
            options={Object.entries(REASON_LABEL).map(([value, label]) => ({ value, label }))}
            onChange={(v) => {
              setReason(v);
              setPage(1);
            }}
          />
        </>
      }
    >
      <RotationAttentionPanel />
      {jobs.isError ? <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} /> : null}
      <RotationJobsTable
        showAccount
        jobs={jobs.data?.data}
        loading={jobs.isLoading}
        pagination={paginationFor(jobs.data?.total)}
        onResolve={canManage ? setResolving : undefined}
      />
      <ResolveJobModal job={resolving} onClose={() => setResolving(null)} />
    </PageShell>
  );
}
