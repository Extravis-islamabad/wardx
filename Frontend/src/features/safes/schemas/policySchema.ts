import { z } from 'zod';
import { ApproverType, TicketMode } from '@/constants/enums/safes';
import type { ApprovalPolicy } from '@/services/safes-services';

const MAX_PATTERN_LENGTH = 200;

const levelSchema = z
  .object({
    required_approvals: z.number().int().min(1).max(10),
    approver_type: z.enum(ApproverType),
    approver_key: z.string().nullable(),
  })
  .refine((l) => l.approver_type === ApproverType.SAFE_APPROVERS || !!l.approver_key?.trim(), {
    message: 'Name the approver',
    path: ['approver_key'],
  });

/** The backend re-checks everything, including the regex's safety. */
export const policyFormSchema = z
  .object({
    approval_required: z.boolean(),
    levels: z.array(levelSchema).max(5, 'At most 5 levels'),
    ticket_mode: z.enum(TicketMode),
    ticket_pattern: z
      .string()
      .max(MAX_PATTERN_LENGTH)
      .refine((p) => {
        if (!p) return true;
        try {
          new RegExp(p);
          return true;
        } catch {
          return false;
        }
      }, 'Not a valid regular expression'),
    approval_window_minutes: z.number().int().min(1).max(10080),
    approval_multi_use: z.boolean(),
    level_timeout_hours: z.number().int().min(1).max(720),
  })
  .refine((v) => !v.approval_required || v.levels.length > 0, {
    message: 'Add at least one level',
    path: ['levels'],
  });

export type PolicyFormValues = z.infer<typeof policyFormSchema>;

export const policyFormValuesFrom = (p: ApprovalPolicy | undefined): PolicyFormValues => ({
  approval_required: p?.approval_required ?? false,
  levels: (p?.levels ?? []).map((l) => ({
    required_approvals: l.required_approvals,
    approver_type: l.approver_type,
    approver_key: l.approver_key,
  })),
  ticket_mode: p?.ticket_mode ?? TicketMode.OFF,
  ticket_pattern: p?.ticket_pattern ?? '',
  approval_window_minutes: p?.approval_window_minutes ?? 120,
  approval_multi_use: p?.approval_multi_use ?? false,
  level_timeout_hours: p?.level_timeout_hours ?? 24,
});

export const NEW_LEVEL = {
  required_approvals: 1,
  approver_type: ApproverType.SAFE_APPROVERS,
  approver_key: null,
} as const;
