import { useEffect, useRef, useState } from 'react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

// ─── Section definitions ──────────────────────────────────────────────────

const STRUCTURED_SECTIONS = [
  { id: 'dimensions', title: '9 Dimensions', content: 'ARC evaluates datasets across nine dimensions: completeness, uniqueness, consistency, accuracy, timeliness, conformity, integrity, accessibility, and metadata quality. Each dimension contributes a weighted score that determines the overall AI readiness tier.' },
  { id: 'scoring', title: 'Scoring Math', content: 'Scores are deterministic: (pass x 1 + warn x 0.5 + fail x 0) / counted_checks x 100. Deferred checks are excluded. Blocker gating caps the overall score at 59. Tier thresholds: 80+ green, 60-79 yellow, below 60 red.' },
  { id: 'how-it-works', title: 'How ARC Works', content: 'Upload a CSV or connect to a database. ARC profiles columns, runs rule-based checks across all applicable dimensions, computes scores with blocker gating, and optionally generates an LLM narrative with prioritized recommendations.' },
  { id: 'ai-layer', title: 'AI Layer', content: 'The Cortex-backed synthesizer takes the deterministic assessment results and produces a human-readable narrative, key strengths, and prioritized recommendations. The LLM never modifies scores or tier classifications.' },
  { id: 'glossary', title: 'Glossary', content: 'AI Ready: overall score 80+. Conditional: 60-79. Needs Improvement: below 60. Blocker: a severity=blocker rule failure that caps the score. Deferred: a check requiring human attestation, excluded from scoring.' },
]

const UNSTRUCTURED_SECTIONS = [
  { id: 'getting-started', title: 'Getting Started', content: 'Create a product, connect a data source (S3, Azure Blob, Google Drive, or folder upload), and run the ingestion pipeline. PrimeData processes your documents through cleaning, chunking, embedding, and indexing stages.' },
  { id: 'scores', title: 'Understanding Scores', content: 'AI readiness scores reflect document quality across multiple factors: content extractability, structural consistency, metadata completeness, and embedding coverage. Scores update as the pipeline processes more documents.' },
  { id: 'data-quality', title: 'Data Quality', content: 'Quality gates run at each pipeline stage. Preprocessing catches encoding issues and corrupt files. Chunking validates boundary integrity. Indexing verifies embedding dimensions match the configured model.' },
  { id: 'playbooks', title: 'Playbooks', content: 'Nine domain-specific playbooks (Healthcare, Legal, Financial, Regulatory, Academic, Tech, Retail, E-commerce, Scanned) configure processing rules. Each playbook tunes cleaning depth, chunk sizes, and metadata extraction strategies.' },
  { id: 'preprocessing', title: 'Preprocessing', content: 'Documents pass through format detection, text extraction, encoding normalization, and content cleaning. The LLM-assisted cleaning stage can summarize, restructure, or extract metadata from raw document content.' },
  { id: 'vectorization', title: 'Vectorization', content: 'Cleaned chunks are embedded using the configured model and indexed in OpenSearch with their metadata. Vector metadata is the source of truth for search results. Embedding model changes require a full reindex.' },
  { id: 'troubleshooting', title: 'Troubleshooting', content: 'Pipeline failures are retryable by design - all stages are idempotent. Check the Airflow DAG for task-level status. Common issues: connector credentials expired, OpenSearch cluster full, chunk size misconfiguration.' },
  { id: 'best-practices', title: 'Best Practices', content: 'Start with a small representative sample before processing large collections. Use domain-appropriate playbooks. Monitor chunk quality scores before relying on search results. Plan for reindexing when changing embedding models.' },
]

// ─── Component ────────────────────────────────────────────────────────────

export default function HelpCenter() {
  return (
    <section className="container py-12 animate-card-rise">
      {/* Page header */}
      <div className="mb-10">
        <p className="font-nav text-[13px] font-medium uppercase tracking-[0.15em] text-muted-foreground mb-2">
          Help Center
        </p>
        <h1 className="font-display text-4xl md:text-5xl font-light text-primary leading-tight">
          How can we help?
        </h1>
      </div>

      {/* Product tabs */}
      <Tabs defaultValue="structured" className="w-full">
        <TabsList className="mb-8">
          <TabsTrigger value="structured">Structured</TabsTrigger>
          <TabsTrigger value="unstructured">Unstructured</TabsTrigger>
        </TabsList>

        <TabsContent value="structured">
          <HelpContent sections={STRUCTURED_SECTIONS} />
        </TabsContent>

        <TabsContent value="unstructured">
          <HelpContent sections={UNSTRUCTURED_SECTIONS} />
        </TabsContent>
      </Tabs>
    </section>
  )
}

// ─── Sidebar + content layout ─────────────────────────────────────────────

interface Section {
  id: string
  title: string
  content: string
}

function HelpContent({ sections }: { sections: Section[] }) {
  const [activeId, setActiveId] = useState(sections[0]?.id ?? '')
  const sectionRefs = useRef<Map<string, HTMLElement>>(new Map())

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
          }
        }
      },
      { rootMargin: '-20% 0px -60% 0px' },
    )

    for (const el of sectionRefs.current.values()) {
      observer.observe(el)
    }
    return () => observer.disconnect()
  }, [sections])

  return (
    <div className="flex gap-12">
      {/* Sidebar nav (desktop) */}
      <nav className="hidden lg:block w-56 flex-shrink-0">
        <div className="sticky top-20 space-y-1">
          {sections.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={cn(
                'block px-3 py-2 rounded-md text-sm font-medium transition-colors',
                activeId === s.id
                  ? 'bg-accent/10 text-accent'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted',
              )}
            >
              {s.title}
            </a>
          ))}
        </div>
      </nav>

      {/* Mobile section strip */}
      <div className="lg:hidden w-full overflow-x-auto scrollbar-none mb-6 -mt-2">
        <div className="flex gap-2 pb-2">
          {sections.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={cn(
                'whitespace-nowrap px-3 py-1.5 rounded-full text-xs font-medium transition-colors border',
                activeId === s.id
                  ? 'bg-accent/10 text-accent border-accent/20'
                  : 'text-muted-foreground border-border hover:text-foreground',
              )}
            >
              {s.title}
            </a>
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 min-w-0 space-y-12">
        {sections.map((s) => (
          <div
            key={s.id}
            id={s.id}
            ref={(el) => { if (el) sectionRefs.current.set(s.id, el) }}
            className="scroll-mt-24"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-1 h-7 rounded-full bg-accent" />
              <h2 className="font-display text-2xl font-light text-foreground">
                {s.title}
              </h2>
            </div>
            <p className="text-muted-foreground leading-relaxed pl-[19px]">
              {s.content}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
