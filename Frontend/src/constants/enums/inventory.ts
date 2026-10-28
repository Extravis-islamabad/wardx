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

export const DEFAULT_PLATFORM = 'cisco_ios';

export enum Protocol {
  SSH = 'ssh',
  TELNET = 'telnet',
  RDP = 'rdp',
  VNC = 'vnc',
  HTTPS = 'https',
  DB = 'db',
}

export const SECRET_TYPES: { value: string; label: string }[] = [
  { value: 'password', label: 'Password' },
  { value: 'enable_secret', label: 'Enable secret' },
  { value: 'ssh_key', label: 'SSH private key' },
  { value: 'api_key', label: 'API key' },
];

export const DEFAULT_SECRET_TYPE = 'password';

export const platformLabel = (value: string | null | undefined) =>
  PLATFORMS.find((p) => p.value === value)?.label ?? value ?? '';
