import { z } from 'zod';

/** The backend requires at least 20 characters; the reason is stored, audited and alerted. */
export const emergencyRevealSchema = z.object({
  reason: z.string().trim().min(20, 'Explain the emergency in at least 20 characters').max(2000),
});

export type EmergencyRevealValues = z.infer<typeof emergencyRevealSchema>;
