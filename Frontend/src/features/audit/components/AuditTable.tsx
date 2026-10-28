import type { TableProps, TablePaginationConfig } from 'antd';
import { DataTable, StatusTag } from '@/components';
import { tableStateProps } from '@/lib/tableStateProps';
import { fmtTime } from '@/utils/format';
import type { AuditEvent } from '@/services/audit-services';
import type { useAuditEvents } from '@/features/audit/hooks';

const columns: TableProps<AuditEvent>['columns'] = [
  // The hash-chain sequence is the event's own public number, not an internal key.
  { title: '#', dataIndex: 'seq', key: 'seq', width: 70 },
  { title: 'Time', dataIndex: 'occurred_at', key: 'occurred_at', render: fmtTime, width: 180 },
  { title: 'Actor', dataIndex: 'actor_name', key: 'actor_name' },
  { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <code>{a}</code> },
  { title: 'Object', key: 'object', render: (_, e) => e?.object_type ?? '—' },
  { title: 'Outcome', dataIndex: 'outcome', key: 'outcome', render: (o: string) => <StatusTag label={o} /> },
  { title: 'Source IP', dataIndex: 'source_ip', key: 'source_ip', render: (v: string | null) => v ?? '—' },
];

export function AuditTable({
  query,
  pagination,
}: {
  query: ReturnType<typeof useAuditEvents>;
  pagination: TablePaginationConfig;
}) {
  return (
    <DataTable<AuditEvent>
      rowKey="seq"
      size="small"
      {...tableStateProps(query, "Couldn't load the audit trail")}
      dataSource={query?.data?.data}
      pagination={pagination}
      expandable={{
        expandedRowRender: (e) => (
          <pre className="m-0 text-xs">
            {JSON.stringify({ ...e?.details, object_id: e?.object_id, hash: e?.hash }, null, 2)}
          </pre>
        ),
      }}
      columns={columns}
    />
  );
}

export default AuditTable;
