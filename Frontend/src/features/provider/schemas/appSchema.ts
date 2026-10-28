import { z } from 'zod';
import type { AppIdentity } from '@/services/provider-services';

/** One CIDR or address per line (or comma separated); the backend validates and normalises. */
export const parseAllowlist = (text: string): string[] =>
  text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);

export const appFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Required')
    .max(100)
    .regex(/^[A-Za-z0-9][A-Za-z0-9._-]*$/, 'Letters, digits and . _ - only'),
  description: z.string().max(2000).optional(),
  enabled: z.boolean(),
  ip_allowlist: z.string().max(10000),
  rate_limit_per_minute: z.number().int().min(1).max(100000),
});

export type AppFormValues = z.infer<typeof appFormSchema>;

export const appFormDefaults: AppFormValues = {
  name: '',
  description: '',
  enabled: true,
  ip_allowlist: '',
  rate_limit_per_minute: 600,
};

export const appFormValuesFrom = (app: AppIdentity | null | undefined): AppFormValues =>
  app
    ? {
        name: app.name,
        description: app.description ?? '',
        enabled: app.enabled,
        ip_allowlist: app.ip_allowlist.join('\n'),
        rate_limit_per_minute: app.rate_limit_per_minute,
      }
    : appFormDefaults;
