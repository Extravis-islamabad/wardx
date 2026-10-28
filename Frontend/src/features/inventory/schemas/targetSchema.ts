import { z } from 'zod';
import { DEFAULT_PLATFORM, Protocol } from '@/constants/enums/inventory';
import type { Target } from '@/services/inventory-services';

export const targetFormSchema = z.object({
  name: z.string().trim().min(1, 'Required').max(255),
  address: z.string().trim().min(1, 'Required').max(255),
  platform: z.string().min(1, 'Required'),
  protocol: z.enum(Protocol),
  port: z.number().int().min(1).max(65535).nullable(),
  description: z.string().max(2000).optional(),
  tags: z.array(z.string()),
  // Rotation: the per-target switch (off by default) and device caps on the password.
  rotation_allowed: z.boolean(),
  min_length: z.number().int().min(12).max(128).nullable(),
  max_length: z.number().int().min(12).max(128).nullable(),
});

export type TargetFormValues = z.infer<typeof targetFormSchema>;

export const targetFormDefaults: TargetFormValues = {
  name: '',
  address: '',
  platform: DEFAULT_PLATFORM,
  protocol: Protocol.SSH,
  port: null,
  description: '',
  tags: [],
  rotation_allowed: false,
  min_length: null,
  max_length: null,
};

export const targetFormValuesFrom = (target: Target | null | undefined): TargetFormValues =>
  target
    ? {
        name: target.name,
        address: target.address,
        platform: target.platform,
        protocol: target.protocol as Protocol,
        port: target.port ?? null,
        description: target.description ?? '',
        tags: target.tags ?? [],
        rotation_allowed: !!target.rotation_allowed,
        min_length: (target.policy_overrides?.min_length as number | undefined) ?? null,
        max_length: (target.policy_overrides?.max_length as number | undefined) ?? null,
      }
    : targetFormDefaults;

/** The API body: length caps travel as policy_overrides (other override keys are kept). */
export const targetPayloadFrom = (values: TargetFormValues, target?: Target | null) => {
  const { min_length, max_length, ...rest } = values;
  const overrides: Target['policy_overrides'] = { ...(target?.policy_overrides ?? {}) };
  delete overrides.min_length;
  delete overrides.max_length;
  if (min_length) overrides.min_length = min_length;
  if (max_length) overrides.max_length = max_length;
  return { ...rest, port: values.port ?? undefined, policy_overrides: overrides };
};
