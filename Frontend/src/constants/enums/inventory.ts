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

/** Platforms rotated over a TLS API (MikroTik API-SSL): they also pin a TLS certificate. */
export const TLS_API_PLATFORMS: readonly string[] = ['mikrotik_routeros'];
export const API_SSL_DEFAULT_PORT = 8729;
export const usesTlsApi = (platform: string | null | undefined) => !!platform && TLS_API_PLATFORMS.includes(platform);

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
  { value: 'snmp_v2c', label: 'SNMP v2c community' },
  { value: 'snmp_v3', label: 'SNMP v3 (USM)' },
];

/** SNMP accounts store a structured secret (one sealed document), not a single value. */
export const isSnmpType = (secretType: string | null | undefined) => !!secretType?.startsWith('snmp_');

export const SNMP_SECURITY_LEVELS = ['noAuthNoPriv', 'authNoPriv', 'authPriv'] as const;
export const SNMP_AUTH_PROTOCOLS = ['MD5', 'SHA', 'SHA-224', 'SHA-256', 'SHA-384', 'SHA-512'] as const;
export const SNMP_PRIV_PROTOCOLS = ['DES', '3DES', 'AES', 'AES-192', 'AES-256'] as const;

export const DEFAULT_SECRET_TYPE = 'password';

export const platformLabel = (value: string | null | undefined) =>
  PLATFORMS.find((p) => p.value === value)?.label ?? value ?? '';
