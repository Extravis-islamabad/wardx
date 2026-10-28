import { SafetyOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useState } from 'react';
import { Button, PageShell } from '@/components';
import { usePagination } from '@/hooks';
import { AuditTable, ChainVerificationResult } from '@/features/audit/components';
import { useAuditEvents, useVerifyAuditChain } from '@/features/audit/hooks';

const AUDIT_PAGE_SIZE = 50;

export default function AuditTrail() {
  const [action, setAction] = useState('');
  const { page, page_size, setPage, paginationFor } = usePagination({ defaultPageSize: AUDIT_PAGE_SIZE });
  const events = useAuditEvents({ page, page_size, action: action || undefined });
  const verify = useVerifyAuditChain();

  return (
    <PageShell
      title="Audit trail"
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Action, e.g. secret.reveal"
            onSearch={(v) => {
              setAction(v.trim());
              setPage(1);
            }}
          />
          <Button icon={<SafetyOutlined />} loading={verify.isPending} onClick={() => verify.mutate()}>
            Verify integrity
          </Button>
        </>
      }
    >
      <ChainVerificationResult result={verify.data} error={verify.error} />
      <AuditTable query={events} pagination={paginationFor(events.data?.total)} />
    </PageShell>
  );
}
