import * as React from 'react';
import { cva } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2.5 py-0.5 font-nav text-[11px] font-semibold tracking-wide uppercase transition-colors',
  {
    variants: {
      variant: {
        default:     'border-transparent bg-primary text-primary-foreground',
        secondary:   'border-transparent bg-secondary text-secondary-foreground',
        destructive: 'border-transparent bg-destructive text-destructive-foreground',
        outline:     'border-border text-foreground',
        // Tier verdicts
        green:  'border-tier-green-base/25 bg-tier-green-light text-tier-green-base',
        yellow: 'border-tier-amber-base/25 bg-tier-amber-light text-tier-amber-base',
        red:    'border-tier-red-base/25 bg-tier-red-light text-tier-red-base',
        // Recommendation severities
        high:   'border-transparent bg-tier-red-light text-tier-red-base',
        medium: 'border-transparent bg-tier-amber-light text-tier-amber-base',
        low:    'border-transparent bg-tier-green-light text-tier-green-base',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

function Badge({ className, variant, ...props }) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
