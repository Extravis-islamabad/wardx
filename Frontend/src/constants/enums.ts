export enum Role {
  Admin = 'admin',
  Approver = 'approver',
  Auditor = 'auditor',
  User = 'user',
}

export const PLATFORMS: { value: string; label: string }[] = [
  { value: 'cisco_ios', label: 'Cisco IOS / IOS-XE' },
  { value: 'cisco_nxos', label: 'Cisco NX-OS' },
  { value: 'huawei_vrp', label: 'Huawei VRP' },
  { value: 'h3c_comware', label: 'H3C Comware' },
  { value: 'juniper_junos', label: 'Juniper Junos' },
  { value: 'mikrotik_routeros', label: 'MikroTik RouterOS' },
  { value: 'fortinet_fortios', label: 'Fortinet FortiOS' },
  { value: 'paloalto_panos', label: 'Palo Alto PAN-OS' },
  { value: 'linux', label: 'Linux / Unix' },
  { value: 'windows', label: 'Windows' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'mssql', label: 'SQL Server' },
  { value: 'generic', label: 'Other' },
];

export const PROTOCOLS = ['ssh', 'telnet', 'rdp', 'vnc', 'https', 'db'] as const;

export const SECRET_TYPES: { value: string; label: string }[] = [
  { value: 'password', label: 'Password' },
  { value: 'enable_secret', label: 'Enable secret' },
  { value: 'ssh_key', label: 'SSH private key' },
  { value: 'api_key', label: 'API key' },
];

export const platformLabel = (value: string) =>
  PLATFORMS.find((p) => p.value === value)?.label ?? value;

export const STATUS_COLORS: Record<string, string> = {
  pending: 'gold',
  approved: 'green',
  denied: 'red',
  cancelled: 'default',
  expired: 'default',
  used: 'blue',
  active: 'green',
  returned: 'default',
  revoked: 'red',
  success: 'green',
  closed: 'default',
  terminated: 'red',
  failed: 'orange',
  allowed: 'green',
  blocked: 'red',
  failure: 'red',
};
