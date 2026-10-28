import { Switch, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { platformLabel } from '@/constants/enums/inventory';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { CommandRule } from '@/services/sessions-services';
import type { useCommandRules } from '@/features/sessions/hooks';

interface CommandRulesTableProps {
  query: ReturnType<typeof useCommandRules>;
  canManage: boolean;
  targetName: (id: string) => string;
  onToggle: (rule: CommandRule, isActive: boolean) => void;
  onDelete: (rule: CommandRule) => void;
}

const AppliesTo = ({ rule, targetName }: { rule: CommandRule; targetName: (id: string) => string }) => {
  if (rule?.platform) return <StatusTag label={platformLabel(rule.platform)} variant={StatusVariant.OUTLINE} />;
  if (rule?.target_id) return <StatusTag label={targetName(rule.target_id)} variant={StatusVariant.INFO} />;
  if (rule?.account_id) return <StatusTag label="one account" variant={StatusVariant.PRIMARY} />;
  return <StatusTag label="everything" variant={StatusVariant.WARNING} />;
};

export function CommandRulesTable({ query, canManage, targetName, onToggle, onDelete }: CommandRulesTableProps) {
  const columns: TableProps<CommandRule>['columns'] = [
    { title: 'Pattern', dataIndex: 'pattern', key: 'pattern', render: (p: string) => <code>{p}</code> },
    { title: 'Message', dataIndex: 'description', key: 'description', render: (d: string | null) => d ?? '—' },
    { title: 'Applies to', key: 'applies_to', render: (_, r) => <AppliesTo rule={r} targetName={targetName} /> },
    {
      title: 'Active',
      key: 'is_active',
      render: (_, r) => (
        <Switch
          size="small"
          aria-label="Rule active"
          checked={r?.is_active}
          disabled={!canManage}
          onChange={(isActive) => onToggle(r, isActive)}
        />
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 90,
      render: (_, r) => (
        <Button variant="danger" size="small" onClick={() => onDelete(r)}>
          Delete
        </Button>
      ),
    },
  ];

  return (
    <DataTable<CommandRule>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load command rules")}
      dataSource={query?.data}
      pagination={false}
      columns={canManage ? columns : columns?.filter((c) => c?.key !== 'actions')}
    />
  );
}

export default CommandRulesTable;
