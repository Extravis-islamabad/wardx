import { z } from 'zod';

export const loginFormSchema = z.object({
  username: z.string().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
});

export type LoginFormValues = z.infer<typeof loginFormSchema>;

export const loginFormDefaults: LoginFormValues = { username: '', password: '' };
