import { Input, Select } from 'antd';
import { FormField } from '@/components';
import { SNMP_AUTH_PROTOCOLS, SNMP_PRIV_PROTOCOLS, SNMP_SECURITY_LEVELS } from '@/constants/enums/inventory';
import type { SnmpSecret } from '@/services/inventory-services';

type V3 = Extract<SnmpSecret, { version: '3' }>;

export const emptySnmpSecret = (secretType: string): SnmpSecret =>
  secretType === 'snmp_v3'
    ? { version: '3', security_name: '', security_level: 'authPriv', auth_protocol: 'SHA-256', priv_protocol: 'AES' }
    : { version: '2c', community: '' };

/** What is sent: fields the security level does not use are left out (the backend refuses them). */
export const snmpPayload = (s: SnmpSecret): SnmpSecret => {
  if (s.version === '2c') return s;
  const out: V3 = { version: '3', security_name: s.security_name, security_level: s.security_level };
  if (s.security_level !== 'noAuthNoPriv') {
    out.auth_protocol = s.auth_protocol;
    out.auth_password = s.auth_password;
  }
  if (s.security_level === 'authPriv') {
    out.priv_protocol = s.priv_protocol;
    out.priv_password = s.priv_password;
  }
  return out;
};

const options = (values: readonly string[]) => values.map((v) => ({ value: v, label: v }));

/** The structured SNMP secret: a v2c community, or SNMPv3 USM fields by security level. */
export function SnmpSecretFields({ value, onChange }: { value: SnmpSecret; onChange: (v: SnmpSecret) => void }) {
  if (value.version === '2c') {
    return (
      <FormField label="Community" htmlFor="snmp-community" required hint="Encrypted in the vault, never shown in lists">
        <Input.Password
          id="snmp-community"
          autoComplete="new-password"
          value={value.community}
          onChange={(e) => onChange({ ...value, community: e.target.value })}
        />
      </FormField>
    );
  }
  const set = (patch: Partial<V3>) => onChange({ ...value, ...patch });
  const auth = value.security_level !== 'noAuthNoPriv';
  const priv = value.security_level === 'authPriv';
  return (
    <>
      <div className="grid grid-cols-2 gap-4">
        <FormField label="Security name" htmlFor="snmp-user" required>
          <Input id="snmp-user" value={value.security_name} onChange={(e) => set({ security_name: e.target.value })} />
        </FormField>
        <FormField label="Security level" htmlFor="snmp-level">
          <Select
            id="snmp-level"
            className="w-full"
            value={value.security_level}
            options={options(SNMP_SECURITY_LEVELS)}
            onChange={(v) => set({ security_level: v })}
          />
        </FormField>
      </div>
      {auth && (
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Auth protocol" htmlFor="snmp-auth-proto">
            <Select
              id="snmp-auth-proto"
              className="w-full"
              value={value.auth_protocol}
              options={options(SNMP_AUTH_PROTOCOLS)}
              onChange={(v) => set({ auth_protocol: v })}
            />
          </FormField>
          <FormField label="Auth password" htmlFor="snmp-auth-pw" required hint="At least 8 characters">
            <Input.Password
              id="snmp-auth-pw"
              autoComplete="new-password"
              value={value.auth_password ?? ''}
              onChange={(e) => set({ auth_password: e.target.value })}
            />
          </FormField>
        </div>
      )}
      {priv && (
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Privacy protocol" htmlFor="snmp-priv-proto">
            <Select
              id="snmp-priv-proto"
              className="w-full"
              value={value.priv_protocol}
              options={options(SNMP_PRIV_PROTOCOLS)}
              onChange={(v) => set({ priv_protocol: v })}
            />
          </FormField>
          <FormField label="Privacy password" htmlFor="snmp-priv-pw" required hint="At least 8 characters">
            <Input.Password
              id="snmp-priv-pw"
              autoComplete="new-password"
              value={value.priv_password ?? ''}
              onChange={(e) => set({ priv_password: e.target.value })}
            />
          </FormField>
        </div>
      )}
    </>
  );
}

export default SnmpSecretFields;
