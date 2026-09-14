import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import Header, { Footer } from '@/components/Header'

interface LayoutProps {
  variant?: 'red' | 'crimson' | 'white'
  children: ReactNode
}

export default function Layout({ variant = 'red', children }: LayoutProps) {
  const modeClass =
    variant === 'crimson' ? 'crimson-mode' :
    variant === 'red' ? 'red-mode' : ''
  const onTinted = variant === 'red' || variant === 'crimson'

  return (
    <div
      className={cn(
        'relative isolate min-h-screen flex flex-col overflow-x-hidden bg-background text-foreground transition-colors duration-300',
        modeClass,
      )}
    >
      <EdgeVignettes variant={variant} />
      <Header onTinted={onTinted} />
      <main className="relative z-10 flex-1 flex flex-col">{children}</main>
      <Footer onTinted={onTinted} />
    </div>
  )
}

function EdgeVignettes({ variant }: { variant: string }) {
  const tintedTop =
    variant === 'crimson'
      ? 'from-[hsl(var(--lilly-dred)/0.72)] via-[hsl(var(--lilly-dred)/0.28)] to-transparent'
      : 'from-[hsl(var(--lilly-dred)/0.64)] via-[hsl(var(--lilly-dred)/0.24)] to-transparent'
  const tintedBottom =
    variant === 'crimson'
      ? 'from-[hsl(var(--lilly-dred)/0.76)] via-[hsl(var(--lilly-dred)/0.3)] to-transparent'
      : 'from-[hsl(var(--lilly-dred)/0.68)] via-[hsl(var(--lilly-dred)/0.26)] to-transparent'
  const neutralTop = 'from-black/12 via-black/5 to-transparent'
  const neutralBottom = 'from-black/14 via-black/6 to-transparent'

  return (
    <>
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-x-0 top-0 z-0 h-36 sm:h-44 bg-gradient-to-b',
          variant === 'red' || variant === 'crimson' ? tintedTop : neutralTop,
        )}
      />
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-x-0 bottom-0 z-0 h-40 sm:h-48 bg-gradient-to-t',
          variant === 'red' || variant === 'crimson' ? tintedBottom : neutralBottom,
        )}
      />
    </>
  )
}
