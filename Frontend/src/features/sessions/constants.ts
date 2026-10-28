import type { GatewaySession } from '@/services/sessions-services';

/** Which slice of sessions the page lists. */
export enum SessionScope {
  ALL = 'all',
  ACTIVE = 'active',
  MINE = 'mine',
}

/** What a command rule applies to. */
export enum RuleScope {
  GLOBAL = 'global',
  PLATFORM = 'platform',
  TARGET = 'target',
}

export enum SessionDrawerTab {
  REPLAY = 'replay',
  COMMANDS = 'commands',
}

export const RULE_SCOPE_OPTIONS = [
  { value: RuleScope.GLOBAL, label: 'Every session' },
  { value: RuleScope.PLATFORM, label: 'One platform' },
  { value: RuleScope.TARGET, label: 'One target' },
];

/** Wall-clock length of a session; a live one runs to now. */
export const sessionDuration = (s: GatewaySession) => {
  const end = s?.ended_at ? new Date(s.ended_at) : new Date();
  const secs = Math.max(0, Math.round((end.getTime() - new Date(s?.started_at).getTime()) / 1000));
  const m = Math.floor(secs / 60);
  return m ? `${m}m ${secs % 60}s` : `${secs}s`;
};
