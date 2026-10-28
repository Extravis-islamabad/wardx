import { zodResolver } from '@hookform/resolvers/zod';
import { Checkbox, Input, Modal, Radio, Select, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { PrincipalType, SAFE_PERMISSION_OPTIONS } from '@/constants/enums/safes';
import { useAuth } from '@/context/AuthContext';
import { useUsers } from '@/features/identity/hooks';
import { useAddSafeMember } from '@/features/safes/hooks';
import { memberFormDefaults, memberFormSchema, type MemberFormValues } from '@/features/safes/schemas/safeSchema';
import type { Safe } from '@/services/safes-services';
import { notify } from '@/utils/notify';

const USER_SEARCH_PAGE = { page: 1, page_size: 20 } as const;

/** Add a WardX user (searched by name) or a directory group (by DN) with chosen permissions. */
export function AddMemberModal({ safe, onClose }: { safe: Safe | null; onClose: () => void }) {
  const { canAccess } = useAuth();
  // Searching users needs users.manage; others enter the user's id.
  const canSearchUsers = canAccess({ permission: PERMISSIONS.USERS_MANAGE });
  const [search, setSearch] = useState('');
  const { mutateAsync: addMember, isPending } = useAddSafeMember(safe?.id ?? '');
  const {
    control,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<MemberFormValues>({ resolver: zodResolver(memberFormSchema), defaultValues: memberFormDefaults });
  const principalType = useWatch({ control, name: 'principal_type' });
  const users = useUsers(
    { ...USER_SEARCH_PAGE, search: search || undefined },
    { enabled: !!safe && canSearchUsers && principalType === PrincipalType.USER },
  );

  useEffect(() => {
    if (safe) reset(memberFormDefaults);
  }, [safe, reset]);

  const onSubmit = async (values: MemberFormValues) => {
    try {
      await addMember(values);
      notify.success('Member added');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure (self_grant_forbidden included).
    }
  };

  return (
    <Modal
      open={!!safe}
      title={<ModalTitle>{`Add member to ${safe?.name ?? ''}`}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
      width={560}
    >
      <Box className="px-2 border-0">
        <FormField label="Member" htmlFor="member-type">
          <Controller
            control={control}
            name="principal_type"
            render={({ field }) => (
              <Radio.Group
                id="member-type"
                value={field.value}
                onChange={(e) => {
                  field.onChange(e.target.value);
                  setValue('principal_key', '');
                }}
                options={[
                  { value: PrincipalType.USER, label: 'WardX user' },
                  { value: PrincipalType.GROUP, label: 'Directory group' },
                ]}
              />
            )}
          />
        </FormField>
        {principalType === PrincipalType.USER ? (
          <FormField
            label="User"
            htmlFor="member-user"
            required
            error={errors.principal_key?.message}
            hint={canSearchUsers ? undefined : "Enter the user's id (searching users needs users.manage)."}
          >
            <Controller
              control={control}
              name="principal_key"
              render={({ field }) =>
                canSearchUsers ? (
                  <Select
                    id="member-user"
                    className="w-full"
                    showSearch
                    filterOption={false}
                    value={field.value || undefined}
                    onSearch={setSearch}
                    onChange={field.onChange}
                    loading={users.isLoading}
                    placeholder="Search by username or name"
                    options={users.data?.data?.map((u) => ({
                      value: u.id,
                      label: `${u.username}${u.full_name ? ` (${u.full_name})` : ''}`,
                    }))}
                  />
                ) : (
                  <Input {...field} id="member-user" placeholder="00000000-0000-0000-0000-000000000000" />
                )
              }
            />
          </FormField>
        ) : (
          <FormField
            label="Group distinguished name"
            htmlFor="member-group"
            required
            error={errors.principal_key?.message}
            hint="Members of nested groups count too on Active Directory (when nested groups are on)."
          >
            <Controller
              control={control}
              name="principal_key"
              render={({ field }) => (
                <Input
                  {...field}
                  id="member-group"
                  className="font-mono"
                  placeholder="cn=NOC-Operators,ou=groups,dc=corp,dc=example"
                />
              )}
            />
          </FormField>
        )}
        <FormField label="Permissions" htmlFor="member-permissions" required error={errors.permissions?.message}>
          <Controller
            control={control}
            name="permissions"
            render={({ field }) => (
              <Checkbox.Group value={field.value} onChange={field.onChange} className="grid! grid-cols-2 gap-1">
                {SAFE_PERMISSION_OPTIONS.map((o) => (
                  <Tooltip key={o.value} title={o.hint} placement="left">
                    <Checkbox value={o.value}>{o.label}</Checkbox>
                  </Tooltip>
                ))}
              </Checkbox.Group>
            )}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
            Add
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default AddMemberModal;
