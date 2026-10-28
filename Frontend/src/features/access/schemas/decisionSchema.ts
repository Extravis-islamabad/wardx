import { z } from 'zod';

export const decisionFormSchema = z.object({
  note: z.string().max(2000).optional(),
});

export type DecisionFormValues = z.infer<typeof decisionFormSchema>;

export const decisionFormDefaults: DecisionFormValues = { note: '' };
