import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Merge Tailwind class strings, deduplicating conflicting utilities.
// Standard shadcn/ui helper used by every component.
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
