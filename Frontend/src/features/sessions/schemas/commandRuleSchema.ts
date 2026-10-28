import { z } from 'zod';
import { RuleScope } from '@/features/sessions/constants';

const isRegex = (v: string) => {
  try {
    new RegExp(v);
    return true;
  } catch {
    return false;
  }
};

export const commandRuleFormSchema = z.object({
  pattern: z.string().min(1, 'Required').max(500).refine(isRegex, 'Not a valid regular expression'),
  description: z.string().max(500).optional(),
  scope: z.enum(RuleScope),
  platform: z.string().optional(),
  target_id: z.string().optional(),
});

export type CommandRuleFormValues = z.infer<typeof commandRuleFormSchema>;

export const commandRuleFormDefaults: CommandRuleFormValues = {
  pattern: '',
  description: '',
  scope: RuleScope.GLOBAL,
};
