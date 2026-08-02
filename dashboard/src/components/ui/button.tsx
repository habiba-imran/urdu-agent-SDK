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
  /** Accessible name. Required in practice for icon-only buttons. */
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
    default: 'bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50',
    secondary: 'bg-muted text-foreground hover:bg-muted/70 disabled:opacity-50',
    outline: 'border border-border bg-transparent hover:bg-muted/50 disabled:opacity-50',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
  };

  const sizes: Record<ButtonSize, string> = {
    md: 'px-3 py-1.5 text-sm',
    sm: 'px-2.5 py-1 text-xs',
  };

  return (
    <button
      ref={ref}
      type={type}
      title={title}
      aria-label={ariaLabel}
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
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
