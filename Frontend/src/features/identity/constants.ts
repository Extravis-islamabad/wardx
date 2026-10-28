import { Role } from '@/constants/enums/auth';
import { StatusVariant } from '@/constants/enums/status';
import { SyncStatus } from '@/constants/enums/identity';

export const ROLE_OPTIONS = [
  { value: Role.USER, label: 'User — checks out credentials' },
  { value: Role.APPROVER, label: 'Approver — decides requests' },
  { value: Role.AUDITOR, label: 'Auditor — reads the audit trail' },
  { value: Role.ADMIN, label: 'Administrator' },
];

/** Bare role names, for compact pickers (table cells, group mappings). */
export const ROLE_SHORT_OPTIONS = [Role.ADMIN, Role.APPROVER, Role.AUDITOR, Role.USER].map((r) => ({ value: r, label: r }));

export enum DirectoryPreset {
  AD = 'ad',
  OPENLDAP = 'openldap',
}

export const DIRECTORY_PRESETS: Record<
  DirectoryPreset,
  {
    label: string;
    user_filter: string;
    attr_username: string;
    attr_email: string;
    attr_full_name: string;
    group_base_dn: string;
    group_filter: string;
    /** Resolve nested groups (LDAP_MATCHING_RULE_IN_CHAIN): AD only. */
    nested_groups: boolean;
  }
> = {
  [DirectoryPreset.AD]: {
    label: 'Active Directory',
    user_filter: '(&(objectClass=user)(sAMAccountName={username}))',
    attr_username: 'sAMAccountName',
    attr_email: 'mail',
    attr_full_name: 'displayName',
    group_base_dn: '',
    group_filter: '',
    nested_groups: true,
  },
  [DirectoryPreset.OPENLDAP]: {
    label: 'OpenLDAP',
    user_filter: '(&(objectClass=inetOrgPerson)(uid={username}))',
    attr_username: 'uid',
    attr_email: 'mail',
    attr_full_name: 'cn',
    group_base_dn: '',
    group_filter: '(&(objectClass=groupOfNames)(member={user_dn}))',
    nested_groups: false,
  },
};

/** Select value standing in for "no default role", which the API expresses as null. */
export const DENY_DEFAULT_ROLE = '__deny';

export const SYNC_STATUS_VARIANT: Record<SyncStatus, StatusVariant> = {
  [SyncStatus.OK]: StatusVariant.SUCCESS,
  [SyncStatus.NEEDS_REVIEW]: StatusVariant.WARNING,
  [SyncStatus.FAILED]: StatusVariant.DANGER,
};
