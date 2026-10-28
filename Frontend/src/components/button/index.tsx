import { Button as AntdButton, type ButtonProps as AntButtonProps } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import React, { forwardRef } from 'react';

/**
 * The colour role, not the appearance. Pick by what the button *does*:
 * `primary` confirms, `admin` cancels or is a row action, `danger` destroys.
 */
export type ButtonVariant = 'default' | 'primary' | 'outline' | 'ghost' | 'admin' | 'danger' | 'success' | 'warning';
type ButtonSize = 'small' | 'medium' | 'large';

const variantClasses: Record<ButtonVariant, string> = {
  default: '',
  primary:
    'bg-(--primary)! text-(--status-on-solid)! border-(--primary)! hover:bg-(--primary-hover)! hover:border-(--primary-hover)!',
  outline: 'bg-transparent! border! border-(--border)! text-(--foreground)! hover:bg-(--muted)!',
  ghost: 'bg-transparent! border-0! text-(--primary)! hover:bg-(--muted)!',
  admin: 'bg-(--card)! border! border-(--border)! text-(--foreground)! hover:bg-(--muted)!',
  danger:
    'bg-(--danger)! text-(--status-on-solid)! border-(--danger)! hover:bg-(--danger-hover)! hover:border-(--danger-hover)!',
  success: 'bg-(--success)! text-(--status-on-solid)! border-(--success)! hover:opacity-90!',
  warning: 'bg-(--warning)! text-(--status-on-solid)! border-(--warning)! hover:opacity-90!',
};

const sizeClasses: Record<ButtonSize, string> = {
  small: 'h-[24px]! px-2! text-[12px]! font-semibold! leading-none!',
  medium: '',
  large: 'px-6! py-3! text-lg!',
};

export interface ButtonProps extends Omit<AntButtonProps, 'type' | 'size' | 'variant'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  type?: 'button' | 'submit' | 'reset';
  children?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'default', size = 'medium', className = '', type = 'button', loading, disabled, icon, children, ...props },
  ref,
) {
  const sizeClass = variant === 'default' ? '' : sizeClasses[size];
  // Variant colours are !important, so they also override antd's disabled look.
  const disabledClass = disabled && variant !== 'default' ? 'opacity-50! cursor-not-allowed!' : '';
  const isLoading = Boolean(loading);
  return (
    <AntdButton
      ref={ref}
      className={`${variantClasses[variant]} ${sizeClass} ${disabledClass} ${className}`.trim()}
      htmlType={type}
      size={size === 'small' ? 'small' : size === 'large' ? 'large' : 'middle'}
      disabled={isLoading || disabled}
      icon={isLoading ? undefined : icon}
      {...props}
    >
      {isLoading ? (
        // The label stays in place but invisible so the button keeps its width.
        <span className="relative inline-flex items-center justify-center">
          <span className="invisible">{children}</span>
          <LoadingOutlined className="absolute" />
        </span>
      ) : (
        children
      )}
    </AntdButton>
  );
});

export default Button;
