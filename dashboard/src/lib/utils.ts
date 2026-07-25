import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge class names, letting later Tailwind classes override earlier ones (a plain
 * `.filter(Boolean).join(' ')` does not resolve Tailwind conflicts — the winner would
 * depend on stylesheet order rather than call order).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
