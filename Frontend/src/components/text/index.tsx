import React from 'react';

export type TextVariant = 'h1' | 'h2' | 'h3' | 'h4' | 'body' | 'body_sm' | 'caption' | 'label' | 'errorInline' | 'inputLabel';

type TextElement = 'span' | 'p' | 'div' | 'h1' | 'h2' | 'h3' | 'h4' | 'label' | 'code';

/** The type scale. Every entry resolves its colour from a theme token. */
const variantClasses: Record<TextVariant, string> = {
  h1: 'text-2xl font-bold leading-8 text-(--foreground)',
  h2: 'text-lg font-semibold leading-6 text-(--foreground)',
  h3: 'text-base font-medium leading-6 text-(--foreground)',
  h4: 'text-xs font-bold leading-[15.6px] text-(--foreground)',
  body: 'text-base font-normal leading-6 text-(--foreground)',
  body_sm: 'text-sm font-normal leading-5 text-(--foreground)',
  caption: 'text-xs font-normal leading-4 text-(--muted-foreground)',
  label: 'text-[10px] font-bold leading-4 text-(--muted-foreground)',
  errorInline: 'text-xs text-(--error)',
  inputLabel: 'text-sm font-medium leading-5 text-(--foreground)',
};

type TextProps = Omit<React.HTMLAttributes<HTMLElement>, 'className'> & {
  as?: TextElement;
  variant?: TextVariant;
  className?: string;
  htmlFor?: string;
  children?: React.ReactNode;
};

export const Text = ({ as = 'p', variant = 'body_sm', className = '', children, ...rest }: TextProps) =>
  React.createElement(as, { className: `m-0 ${variantClasses[variant]} ${className}`.trim(), ...rest }, children);

export default Text;
