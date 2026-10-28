import { z } from 'zod';
import { DEFAULT_SECRET_TYPE } from '@/constants/enums/inventory';
import type { Account } from '@/services/inventory-services';

export const accountFormSchema = z.object({
  target_id: z.string().min(1, 'Choose a target'),
  safe_id: z.string().min(1, 'Choose a safe'),
  username: z.string().trim().min(1, 'Required').max(255),
  secret_type: z.string(),
  description: z.string().max(2000).optional(),
  requires_approval: z.boolean(),
  exclusive_checkout: z.boolean(),
  max_checkout_minutes: z.number().int().min(1).max(1440),
  secret: z.string().max(16384).optional(),
});

export type AccountFormValues = z.infer<typeof accountFormSchema>;

export const accountFormDefaults: AccountFormValues = {
  target_id: '',
  safe_id: '',
  username: '',
  secret_type: DEFAULT_SECRET_TYPE,
  description: '',
  requires_approval: false,
  exclusive_checkout: true,
  max_checkout_minutes: 60,
  secret: '',
};

export const accountFormValuesFrom = (account: Account | null | undefined): AccountFormValues =>
  account
    ? {
        target_id: account.target.id,
        safe_id: account.safe?.id ?? '',
        username: account.username,
        secret_type: account.secret_type,
        description: account.description ?? '',
        requires_approval: account.requires_approval,
        exclusive_checkout: account.exclusive_checkout,
        max_checkout_minutes: account.max_checkout_minutes,
        secret: '',
      }
    : accountFormDefaults;

export const secretFormSchema = z.object({
  value: z.string().min(1, 'Enter the current secret'),
});

export type SecretFormValues = z.infer<typeof secretFormSchema>;

export const secretFormDefaults: SecretFormValues = { value: '' };
