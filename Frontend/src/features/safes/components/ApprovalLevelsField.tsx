import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Button as AntdButton, InputNumber, Select, Space, Typography } from 'antd';
import { Controller, useFieldArray, useWatch, type Control, type FieldErrors } from 'react-hook-form';
import { Button, FieldError } from '@/components';
import { APPROVER_TYPE_OPTIONS, ApproverType, PrincipalType, SafePermission } from '@/constants/enums/safes';
import { NEW_LEVEL, type PolicyFormValues } from '@/features/safes/schemas/policySchema';
import type { SafeMember } from '@/services/safes-services';

interface ApprovalLevelsFieldProps {
  control: Control<PolicyFormValues>;
  errors: FieldErrors<PolicyFormValues>;
  /** The safe's members: named approvers are picked from those holding 'approve'. */
  members: SafeMember[];
  readOnly: boolean;
}

/** Ordered approval levels: who approves at each, and how many approvals it needs. */
export function ApprovalLevelsField({ control, errors, members, readOnly }: ApprovalLevelsFieldProps) {
  const { fields, append, remove, move } = useFieldArray({ control, name: 'levels' });
  const levels = useWatch({ control, name: 'levels' });
  const approvers = members.filter((m) => m.permissions.includes(SafePermission.APPROVE));
  const userOptions = approvers
    .filter((m) => m.principal_type === PrincipalType.USER)
    .map((m) => ({ value: m.principal_key, label: m.display_name ?? m.principal_key }));
  const groupOptions = approvers
    .filter((m) => m.principal_type === PrincipalType.GROUP)
    .map((m) => ({ value: m.principal_key, label: m.principal_key }));

  return (
    <div>
      {fields.map((f, i) => {
        const kind = levels?.[i]?.approver_type;
        return (
          <div key={f.id} className="mb-2 rounded border border-(--border) p-2">
            <Space wrap align="center">
              <Typography.Text strong>Level {i + 1}</Typography.Text>
              <Controller
                control={control}
                name={`levels.${i}.approver_type`}
                render={({ field }) => (
                  <Select
                    {...field}
                    aria-label={`Level ${i + 1} approvers`}
                    className="w-44"
                    disabled={readOnly}
                    options={APPROVER_TYPE_OPTIONS}
                  />
                )}
              />
              {kind === ApproverType.USER && (
                <Controller
                  control={control}
                  name={`levels.${i}.approver_key`}
                  render={({ field }) => (
                    <Select
                      aria-label={`Level ${i + 1} user`}
                      className="w-56"
                      disabled={readOnly}
                      value={field.value || undefined}
                      onChange={field.onChange}
                      placeholder="A member with approve"
                      options={userOptions}
                    />
                  )}
                />
              )}
              {kind === ApproverType.GROUP && (
                <Controller
                  control={control}
                  name={`levels.${i}.approver_key`}
                  render={({ field }) => (
                    <Select
                      aria-label={`Level ${i + 1} group`}
                      className="w-72"
                      disabled={readOnly}
                      value={field.value || undefined}
                      onChange={field.onChange}
                      placeholder="A group member with approve"
                      options={groupOptions}
                    />
                  )}
                />
              )}
              <span>needs</span>
              <Controller
                control={control}
                name={`levels.${i}.required_approvals`}
                render={({ field }) => (
                  <InputNumber {...field} aria-label={`Level ${i + 1} approvals`} min={1} max={10} disabled={readOnly} />
                )}
              />
              <span>{levels?.[i]?.required_approvals === 2 ? 'approvals (dual control)' : 'approval(s)'}</span>
              {!readOnly && (
                <>
                  <AntdButton size="small" aria-label="Move up" icon={<ArrowUpOutlined />} disabled={i === 0} onClick={() => move(i, i - 1)} />
                  <AntdButton
                    size="small"
                    aria-label="Move down"
                    icon={<ArrowDownOutlined />}
                    disabled={i === fields.length - 1}
                    onClick={() => move(i, i + 1)}
                  />
                  <AntdButton size="small" danger aria-label="Remove level" icon={<DeleteOutlined />} onClick={() => remove(i)} />
                </>
              )}
            </Space>
            <FieldError message={errors.levels?.[i]?.approver_key?.message} />
          </div>
        );
      })}
      <FieldError message={errors.levels?.message ?? errors.levels?.root?.message} />
      {!readOnly && fields.length < 5 && (
        <Button variant="admin" size="small" icon={<PlusOutlined />} onClick={() => append({ ...NEW_LEVEL })}>
          Add level
        </Button>
      )}
    </div>
  );
}

export default ApprovalLevelsField;
