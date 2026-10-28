import { StatusVariant } from './status';

/** What a safe member may do (Backend docs/phase1/SAFES_AND_APPROVALS.md, section (a)). */
export enum SafePermission {
  LIST = 'list',
  USE = 'use',
  RETRIEVE = 'retrieve',
  MANAGE_ACCOUNTS = 'manage_accounts',
  MANAGE_MEMBERS = 'manage_members',
  VIEW_AUDIT = 'view_audit',
  APPROVE = 'approve',
  /** Application identities only, and the only permission they hold (credential provider). */
  FETCH = 'fetch',
}

export enum PrincipalType {
  USER = 'user',
  GROUP = 'group',
  /** Migration only (the Default safe's members); shown read-only. */
  ROLE = 'role',
  /** An application identity (credential provider); holds only 'fetch'. */
  APP = 'app',
}

export enum TicketMode {
  OFF = 'off',
  OPTIONAL = 'optional',
  REQUIRED = 'required',
}

export enum ApproverType {
  /** Every safe member holding 'approve'. */
  SAFE_APPROVERS = 'safe_approvers',
  /** A named user, who must hold 'approve' on the safe. */
  USER = 'user',
  /** A directory group (DN), which must be a member with 'approve'. */
  GROUP = 'group',
}

export const APPROVER_TYPE_OPTIONS = [
  { value: ApproverType.SAFE_APPROVERS, label: 'Safe approvers' },
  { value: ApproverType.USER, label: 'Named user' },
  { value: ApproverType.GROUP, label: 'Directory group' },
];

export const TICKET_MODE_OPTIONS = [
  { value: TicketMode.OFF, label: 'Off' },
  { value: TicketMode.OPTIONAL, label: 'Optional' },
  { value: TicketMode.REQUIRED, label: 'Required' },
];

export enum SafeHealthState {
  HEALTHY = 'healthy',
  BREAK_GLASS_ONLY = 'break_glass_only',
  UNREACHABLE = 'unreachable',
}

export const SAFE_PERMISSION_OPTIONS: { value: SafePermission; label: string; hint: string }[] = [
  { value: SafePermission.LIST, label: 'List', hint: 'See the safe and its accounts' },
  { value: SafePermission.USE, label: 'Use', hint: 'Connect through the gateway without seeing the password' },
  { value: SafePermission.RETRIEVE, label: 'Retrieve', hint: 'Check out and reveal' },
  { value: SafePermission.MANAGE_ACCOUNTS, label: 'Manage accounts', hint: 'Add, edit and delete accounts; set secrets' },
  { value: SafePermission.MANAGE_MEMBERS, label: 'Manage members', hint: 'Add, change and remove members' },
  { value: SafePermission.VIEW_AUDIT, label: 'View audit', hint: "Read audit events for the safe's accounts" },
  { value: SafePermission.APPROVE, label: 'Approve', hint: 'Approve access requests' },
];

export const SAFE_HEALTH_TAG: Record<SafeHealthState, { label: string; variant: StatusVariant; hint: string }> = {
  [SafeHealthState.HEALTHY]: {
    label: 'healthy',
    variant: StatusVariant.SUCCESS,
    hint: 'Has a direct user or role member',
  },
  [SafeHealthState.BREAK_GLASS_ONLY]: {
    label: 'break-glass only',
    variant: StatusVariant.WARNING,
    hint: 'Only directory groups: if the directory is down, only break-glass reaches it',
  },
  [SafeHealthState.UNREACHABLE]: {
    label: 'unreachable',
    variant: StatusVariant.DANGER,
    hint: 'Only directory groups and no eligible break-glass holder: a directory outage locks it',
  },
};
