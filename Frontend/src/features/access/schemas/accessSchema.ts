import { z } from 'zod';
import { DEFAULT_ACCESS_MINUTES } from '@/features/access/constants';

export const accessFormSchema = z.object({
  reason: z.string().trim().min(3, 'Give a reason (at least 3 characters)').max(2000),
  ticket_ref: z.string().max(100).optional(),
  duration_minutes: z.number().int().min(1).max(1440),
});

export type AccessFormValues = z.infer<typeof accessFormSchema>;

export const accessFormDefaults = (maxMinutes?: number): AccessFormValues => ({
  reason: '',
  ticket_ref: '',
  duration_minutes: Math.min(DEFAULT_ACCESS_MINUTES, maxMinutes ?? DEFAULT_ACCESS_MINUTES),
});
