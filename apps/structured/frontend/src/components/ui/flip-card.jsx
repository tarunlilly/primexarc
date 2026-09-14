import { useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * FlipCard — 3D flippable card primitive.
 *
 * Usage:
 *   <FlipCard
 *     front={<div>Front content</div>}
 *     back={<div>Back content</div>}
 *     flipped={isFlipped}
 *     onFlip={() => setFlipped(!isFlipped)}
 *     className="h-[200px]"
 *   />
 *
 * Keyboard: Enter/Space to flip, Esc to flip back.
 * Reduced motion: crossfade instead of 3D rotation.
 */
export function FlipCard({ front, back, flipped = false, onFlip, className = '', active = false }) {
  return (
    <div
      className={cn('flip-card-container relative cursor-pointer', className)}
      onClick={onFlip}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFlip?.(); }
        if (e.key === 'Escape' && flipped) { e.preventDefault(); onFlip?.(); }
      }}
      tabIndex={0}
      role="button"
      aria-label={flipped ? 'Showing purpose picker. Press Escape to flip back.' : 'Press Enter to pick a purpose.'}
    >
      <div className={cn(
        'flip-card-inner w-full h-full transition-transform duration-400',
        'motion-reduce:transition-none',
        flipped && 'flip-card-flipped'
      )}>
        {/* Front face */}
        <div className={cn(
          'flip-card-face absolute inset-0 rounded-xl border bg-card overflow-hidden',
          active ? 'border-primary ring-2 ring-primary/20' : 'border-border',
          flipped && 'motion-reduce:opacity-0 motion-reduce:pointer-events-none'
        )}>
          {front}
        </div>
        {/* Back face */}
        <div className={cn(
          'flip-card-face flip-card-back absolute inset-0 rounded-xl border border-border bg-card overflow-hidden',
          !flipped && 'motion-reduce:opacity-0 motion-reduce:pointer-events-none'
        )}>
          {back}
        </div>
      </div>
    </div>
  );
}
