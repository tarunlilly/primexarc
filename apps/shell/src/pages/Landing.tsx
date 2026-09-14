import { Database, FileText, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getStructuredUrl, getUnstructuredUrl } from '@/lib/config'

const doors = [
  {
    key: 'structured',
    title: 'Structured',
    description: 'Assess CSV and database schemas for AI readiness.',
    icon: Database,
    href: getStructuredUrl(),
  },
  {
    key: 'unstructured',
    title: 'Unstructured',
    description: 'Ingest, clean, chunk, embed, and index documents.',
    icon: FileText,
    href: getUnstructuredUrl(),
  },
] as const

export default function Landing() {
  return (
    <section className="flex-1 flex flex-col items-center justify-center px-4">
      <div className="animate-card-rise max-w-4xl w-full text-center">
        {/* Eyebrow */}
        <p className="font-nav text-[13px] font-medium uppercase tracking-[0.15em] text-muted-foreground mb-4">
          Choose your data domain
        </p>

        {/* Headline */}
        <h1 className="font-display text-5xl md:text-6xl lg:text-[72px] font-light text-primary leading-[1.05] mb-16">
          One platform,
          <br />
          two engines.
        </h1>

        {/* Two doors */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
          {doors.map((door, i) => (
            <a
              key={door.key}
              href={door.href}
              className={cn(
                'group relative flex flex-col items-center text-center px-10 py-14',
                'transition-all duration-200 hover:-translate-y-px hover:shadow-md rounded-2xl',
                'hover:bg-muted/60',
                // Vertical divider on the left side of the second panel (desktop only)
                i === 1 && 'md:border-l md:border-border',
              )}
            >
              <door.icon className="h-10 w-10 text-primary/70 mb-6" strokeWidth={1.5} />
              <h2 className="font-display text-3xl font-light text-foreground mb-3">
                {door.title}
              </h2>
              <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px] mb-6">
                {door.description}
              </p>
              <span className="inline-flex items-center gap-2 font-nav text-[13px] font-medium text-muted-foreground/60 group-hover:text-primary transition-colors">
                Open <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
