import { Link } from 'react-router-dom';
import { ArrowRight, Database, ShieldCheck, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

// Home — landing page on the red surface.
// v3 redesign: purpose-aware messaging, three value propositions.

export default function Home() {
  return (
    <div className="bg-grain animate-card-rise">
      <HeroSection />
      <ValuePropsSection />
      <div className="h-20" />
    </div>
  );
}

// ─── Hero ──────────────────────────────────────────────────────────────────
function HeroSection() {
  return (
    <section className="container pt-48 pb-24">
      <div className="max-w-4xl">
        <p className="font-nav text-[13px] font-medium uppercase tracking-[0.15em] text-white/70 mb-8">
          AI-readiness for structured data
        </p>
        <h1 className="font-display text-5xl md:text-6xl lg:text-[72px] font-light leading-[1.05] tracking-[-0.02em] text-white">
          Is your data actually ready for the job you have in mind?
        </h1>
        <p className="mt-8 text-lg md:text-xl text-white/85 max-w-3xl leading-relaxed">
          ARC profiles every table, reads each field to understand what it means,
          checks whether it is permitted for your declared purpose, and returns a
          plain-language report with the specific changes that would make it ready.
          The scoring is deterministic; the language model finds meaning and writes the report.
        </p>
        <div className="mt-10">
          <Button asChild variant="onRed" size="lg">
            <Link to="/assess">
              Start an assessment
              <ArrowRight className="h-4 w-4 ml-2" />
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

// ─── Value propositions ───────────────────────────────────────────────────
function ValuePropsSection() {
  const props = [
    {
      icon: Database,
      title: 'Purpose-aware',
      body: 'The same table can be ready for one use and unfit for another. You declare the purpose; ARC measures against its real requirements.',
    },
    {
      icon: ShieldCheck,
      title: 'Evidence, not vibes',
      body: 'Every finding is quantified from a full scan of your data and stamped with how it was measured.',
    },
    {
      icon: Sparkles,
      title: 'The model reads the data',
      body: 'Field meaning, hidden identifiers and placeholder values are found by reading values, not by matching column names.',
    },
  ];

  return (
    <section className="container py-16">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 max-w-5xl">
        {props.map((prop) => {
          const Icon = prop.icon;
          return (
            <div key={prop.title} className="space-y-3">
              <div className="text-white/70">
                <Icon className="h-6 w-6" strokeWidth={1.5} />
              </div>
              <h3 className="font-display text-xl font-normal text-white">
                {prop.title}
              </h3>
              <p className="text-[15px] text-white/80 leading-relaxed">
                {prop.body}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
