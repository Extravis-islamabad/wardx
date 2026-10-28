import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Input } from 'antd';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Button, FormField } from '@/components';
import { useAuth } from '@/context/AuthContext';
import { loginFormDefaults, loginFormSchema, type LoginFormValues } from '@/features/auth/schemas/loginSchema';
import { errorMessage } from '@/utils/notifyApiError';

/** Username + password step. Sign-in calls skip the toast, so the failure is worded above the form. */
export function LoginForm() {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: loginFormDefaults,
  });

  const onSubmit = async (values: LoginFormValues) => {
    setError(null);
    try {
      await login(values.username, values.password);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      {error && <Alert className="!mb-4" type="error" showIcon title={error} />}
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormField label="Username" htmlFor="login-username" error={errors.username?.message}>
          <Controller
            control={control}
            name="username"
            render={({ field }) => (
              <Input
                {...field}
                id="login-username"
                prefix={<UserOutlined />}
                autoComplete="username"
                autoFocus
                status={errors.username ? 'error' : undefined}
              />
            )}
          />
        </FormField>
        <FormField label="Password" htmlFor="login-password" className="mb-6" error={errors.password?.message}>
          <Controller
            control={control}
            name="password"
            render={({ field }) => (
              <Input.Password
                {...field}
                id="login-password"
                prefix={<LockOutlined />}
                autoComplete="current-password"
                status={errors.password ? 'error' : undefined}
              />
            )}
          />
        </FormField>
        <Button variant="primary" type="submit" block loading={isSubmitting}>
          Sign in
        </Button>
      </form>
    </>
  );
}

export default LoginForm;
