import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import { cn } from '@/lib/utils';

// Custom: accept `indicatorClassName` so the tier color can be passed in.
// The default shadcn Progress only colors via `bg-primary` which we don't want
// on Dashboard (every bar is colored by its dimension's tier).
const Progress = React.forwardRef(
  ({ className, value, indicatorClassName, ...props }, ref) => (
    <ProgressPrimitive.Root
      ref={ref}
      className={cn(
        'relative h-2 w-full overflow-hidden rounded-full bg-muted',
        className,
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn(
          'h-full w-full flex-1 bg-primary transition-transform duration-700 ease-out',
          indicatorClassName,
        )}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  ),
);
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
