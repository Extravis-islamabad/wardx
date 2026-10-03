import { SafetyOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Input, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { STATUS_COLORS } from '@/constants/enums';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { auditApi } from '@/services/api';
import type { AuditEvent } from '@/types/api';

export default function AuditPage() {
  const [action, setAction] = useState('');
  const { page, page_size, setPage, pagination } = usePaging(50);
  const q = { page, page_size, action: action || undefined };
  const { data, isLoading } = useQuery({ queryKey: queryKeys.audit.list(q), queryFn: () => auditApi.list(q) });
  const verify = useMutation({ mutationFn: async () => (await auditApi.verify()).data });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Audit trail</Typography.Title>
        <Space>
          <Input.Search
            allowClear
            placeholder="Action, e.g. secret.reveal"
            onSearch={(v) => { setAction(v.trim()); setPage(1); }}
          />
          <Button icon={<SafetyOutlined />} loading={verify.isPending} onClick={() => verify.mutate()}>
            Verify integrity
          </Button>
        </Space>
      </div>
      {verify.data && (
        <Alert
          className="!mb-4"
          showIcon
          type={verify.data.ok ? 'success' : 'error'}
          title={
            verify.data.ok
              ? `Hash chain intact: ${verify.data.checked} events verified.`
              : `Chain broken at event #${verify.data.broken_at_seq}: ${verify.data.reason}. Events after this point cannot be trusted.`
          }
        />
      )}
      {verify.error && <Alert className="!mb-4" type="error" showIcon title={errorMessage(verify.error)} />}
      <Table<AuditEvent>
        rowKey="seq"
        size="small"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        expandable={{
          expandedRowRender: (e) => (
            <pre className="m-0 text-xs">{JSON.stringify({ ...e.details, object_id: e.object_id, hash: e.hash }, null, 2)}</pre>
          ),
        }}
        columns={[
          { title: '#', dataIndex: 'seq', width: 70 },
          { title: 'Time', dataIndex: 'occurred_at', render: fmtTime, width: 180 },
          { title: 'Actor', dataIndex: 'actor_name' },
          { title: 'Action', dataIndex: 'action', render: (a: string) => <code>{a}</code> },
          { title: 'Object', render: (_, e) => e.object_type ?? '—' },
          { title: 'Outcome', dataIndex: 'outcome', render: (o: string) => <Tag color={STATUS_COLORS[o]}>{o}</Tag> },
          { title: 'Source IP', dataIndex: 'source_ip', render: (v: string | null) => v ?? '—' },
        ]}
      />
    </>
  );
}
