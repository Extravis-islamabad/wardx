import { z } from 'zod';
import { PrincipalType, SafePermission } from '@/constants/enums/safes';
import type { Safe } from '@/services/safes-services';

export const safeFormSchema = z.object({
  name: z.string().trim().min(1, 'Required').max(150),
  description: z.string().max(2000).optional(),
  is_active: z.boolean(),
});

export type SafeFormValues = z.infer<typeof safeFormSchema>;

export const safeFormValuesFrom = (safe: Safe | null | undefined): SafeFormValues => ({
  name: safe?.name ?? '',
  description: safe?.description ?? '',
  is_active: safe?.is_active ?? true,
});

/** The console adds users and directory groups; roles exist only for migrated members. */
export const memberFormSchema = z
  .object({
    principal_type: z.enum([PrincipalType.USER, PrincipalType.GROUP]),
    principal_key: z.string().trim().min(1, 'Required').max(1000),
    permissions: z.array(z.enum(SafePermission)).min(1, 'Choose at least one permission'),
  })
  .refine((v) => v.principal_type !== PrincipalType.GROUP || v.principal_key.includes('='), {
    message: 'A group is named by its distinguished name, e.g. cn=NOC,ou=groups,dc=corp,dc=example',
    path: ['principal_key'],
  });

export type MemberFormValues = z.infer<typeof memberFormSchema>;

export const memberFormDefaults: MemberFormValues = {
  principal_type: PrincipalType.USER,
  principal_key: '',
  permissions: [SafePermission.LIST, SafePermission.RETRIEVE],
};
