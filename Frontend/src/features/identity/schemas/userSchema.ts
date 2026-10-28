import { z } from 'zod';
import { Role } from '@/constants/enums/auth';

const strongPassword = z
  .string()
  .min(12, 'At least 12 characters')
  .refine(
    (v) => [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length >= 3,
    'Mix at least three of: lower case, upper case, digits, symbols',
  );

export const userFormSchema = z.object({
  username: z
    .string()
    .trim()
    .min(3)
    .max(150)
    .regex(/^[A-Za-z0-9._@-]+$/, 'Letters, digits and . _ @ - only'),
  full_name: z.string().max(255).optional(),
  email: z.union([z.literal(''), z.email()]).optional(),
  role: z.enum(Role),
  password: strongPassword,
});

export type UserFormValues = z.infer<typeof userFormSchema>;

export const userFormDefaults: UserFormValues = {
  username: '',
  full_name: '',
  email: '',
  role: Role.USER,
  password: '',
};
