import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <section className="flex-1 flex flex-col items-center justify-center text-center px-4 animate-card-rise">
      <p className="font-nav text-[13px] font-medium uppercase tracking-[0.15em] text-muted-foreground mb-3">
        404
      </p>
      <h1 className="font-display text-5xl md:text-6xl font-light text-primary mb-4">
        Page not found
      </h1>
      <p className="text-muted-foreground text-sm max-w-md mb-8">
        The page you are looking for does not exist or has been moved.
      </p>
      <Button asChild variant="outline" className="gap-2">
        <Link to="/">
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
      </Button>
    </section>
  )
}
