'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export type ButtonVariant = 'default' | 'secondary' | 'outline' | 'destructive';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps {
  className?: string;
  children: React.ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
  'aria-label'?: string;
  title?: string;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    children,
    variant = 'default',
    size = 'md',
    disabled,
    onClick,
    type = 'button',
    title,
    'aria-label': ariaLabel,
  },
  ref,
) {
  const variants: Record<ButtonVariant, string> = {
    default:
      'bg-text text-white hover:opacity-90 disabled:opacity-50',
    secondary:
      'border border-border bg-surface text-text hover:bg-surface-muted disabled:opacity-50',
    outline:
      'border border-border bg-surface text-text hover:bg-surface-muted disabled:opacity-50',
    destructive:
      'border border-border bg-surface text-danger hover:bg-surface-muted disabled:opacity-50',
  };

  const sizes: Record<ButtonSize, string> = {
    md: 'px-5 py-3',
    sm: 'px-4 py-2.5',
  };

  return (
    <button
      ref={ref}
      type={type}
      title={title}
      aria-label={ariaLabel}
      className={cn(
        'inline-flex cursor-pointer items-center justify-center gap-2 rounded-pill font-mono text-[11px] font-medium uppercase tracking-[0.14em] transition-all duration-console',
        sizes[size],
        variants[variant],
        className,
      )}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
});
