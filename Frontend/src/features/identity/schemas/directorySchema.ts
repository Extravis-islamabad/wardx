import { z } from 'zod';
import { Role } from '@/constants/enums/auth';
import { DIRECTORY_PRESETS, DirectoryPreset } from '@/features/identity/constants';
import type { DirectoryConfig } from '@/services/identity-services';

export const directoryFormSchema = z.object({
  enabled: z.boolean(),
  server_url: z.string().regex(/^ldaps?:\/\/\S+$/, 'ldap://host:389 or ldaps://host:636'),
  start_tls: z.boolean(),
  verify_tls: z.boolean(),
  ca_cert_pem: z.string().optional(),
  bind_dn: z.string().min(3, 'Required'),
  bind_password: z.string().optional(),
  user_base_dn: z.string().min(3, 'Required'),
  user_filter: z.string().refine((v) => v.includes('{username}'), 'Must contain {username}'),
  attr_username: z.string().min(1),
  attr_email: z.string().min(1),
  attr_full_name: z.string().min(1),
  group_base_dn: z.string().optional(),
  group_filter: z.string().optional(),
  role_mappings: z.array(z.object({ group_dn: z.string().min(3, 'Group DN'), role: z.enum(Role) })),
  default_role: z.enum(Role).nullable(),
  nested_groups: z.boolean(),
  timeout_seconds: z.number().int().min(1).max(60),
  sync_interval_minutes: z
    .number()
    .int()
    .min(0)
    .max(1440)
    .refine((v) => v === 0 || v >= 5, '0 (off) or at least 5'),
  sync_max_disable_percent: z.number().int().min(1).max(100),
});

export type DirectoryFormValues = z.infer<typeof directoryFormSchema>;

const AD = DIRECTORY_PRESETS[DirectoryPreset.AD];

export const directoryFormValuesFrom = (c: DirectoryConfig | null): DirectoryFormValues => ({
  enabled: c?.enabled ?? false,
  server_url: c?.server_url ?? 'ldaps://dc01.corp.example:636',
  start_tls: c?.start_tls ?? false,
  verify_tls: c?.verify_tls ?? true,
  ca_cert_pem: c?.ca_cert_pem ?? '',
  bind_dn: c?.bind_dn ?? '',
  bind_password: '',
  user_base_dn: c?.user_base_dn ?? '',
  user_filter: c?.user_filter ?? AD.user_filter,
  attr_username: c?.attr_username ?? AD.attr_username,
  attr_email: c?.attr_email ?? 'mail',
  attr_full_name: c?.attr_full_name ?? 'displayName',
  group_base_dn: c?.group_base_dn ?? '',
  group_filter: c?.group_filter ?? '',
  role_mappings: c?.role_mappings ?? [],
  default_role: c?.default_role ?? null,
  // On by default for Active Directory (the in-chain rule is AD-only).
  nested_groups: c?.nested_groups ?? AD.nested_groups,
  timeout_seconds: c?.timeout_seconds ?? 10,
  sync_interval_minutes: c?.sync_interval_minutes ?? 60,
  sync_max_disable_percent: c?.sync_max_disable_percent ?? 20,
});
