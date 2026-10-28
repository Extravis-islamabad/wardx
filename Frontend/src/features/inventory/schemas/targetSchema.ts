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
      }
    : targetFormDefaults;
