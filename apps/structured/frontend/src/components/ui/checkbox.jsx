import * as React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

// Lightweight checkbox - not the full Radix Checkbox primitive since we
// don't need the headless API surface here. A native input with a styled
// overlay covers our case and stays accessible.
const Checkbox = React.forwardRef(({ className, checked, onCheckedChange, ...props }, ref) => (
  <label className={cn(
    'relative inline-flex items-center justify-center w-5 h-5 cursor-pointer',
    className,
  )}>
    <input
      type="checkbox"
      ref={ref}
      checked={checked}
      onChange={(e) => onCheckedChange?.(e.target.checked)}
      className="peer absolute inset-0 opacity-0 cursor-pointer"
      {...props}
    />
    <span className={cn(
      'absolute inset-0 rounded-[5px] border-2 transition-all',
      'peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2',
      checked
        ? 'bg-primary border-primary'
        : 'bg-transparent border-current/40 peer-hover:border-current/70',
    )} />
    {checked && (
      <Check className="relative h-3.5 w-3.5 text-primary-foreground pointer-events-none" strokeWidth={3} />
    )}
  </label>
));
Checkbox.displayName = 'Checkbox';

export { Checkbox };
