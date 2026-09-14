import { useState, useMemo, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight, FileText, RotateCcw, ArrowLeft, CheckCircle2, Loader2, XCircle, AlertTriangle, ShieldAlert, MinusCircle, Search, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { FlipCard } from '@/components/ui/flip-card';
import { LENSES, TIER_STYLES, CHECK_STATUS, tierFor, DIMENSION_TAGS, TAG_STYLES } from '@/lib/dimensions';
import { CAPABILITIES, ARCHETYPE_FAMILIES, LEVEL_LABELS } from '@/lib/capabilities';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Constants ───────────────────────────────────────────────────────────────
const SCORE_COLOR = (s) => s >= 80 ? 'text-tier-green-base' : s >= 60 ? 'text-tier-amber-base' : 'text-tier-red-base';
const BAR_COLOR = (s) => s >= 80 ? 'bg-tier-green-base' : s >= 60 ? 'bg-tier-amber-base' : 'bg-tier-red-base';
const STATUS_WORD = (s) => s >= 80 ? 'strong' : s >= 60 ? 'needs work' : 'at risk';
const SEV_COLORS = {
  blocker: 'bg-tier-red-light text-tier-red-base',
  warning: 'bg-tier-amber-light text-tier-amber-base',
  info: 'bg-muted text-muted-foreground',
};

// Map lens id to archetype family id for back-of-card grouping
const LENS_TO_FAMILIES = {
  DQ: ['baseline'],
  ML: ['model_dev'],
  AI: ['agent_access'],
};

// ─── Main Component ──────────────────────────────────────────────────────────
export default function Dashboard({ result, onRestart, onRescore }) {
  const [flippedCard, setFlippedCard] = useState(null);
  const [selectedPurpose, setSelectedPurpose] = useState(result.selected_archetype || '');
  const [inspectingTable, setInspectingTable] = useState('');
  const [tableSearch, setTableSearch] = useState('');
  const [tableSort, setTableSort] = useState('worst');
  const [showRunbook, setShowRunbook] = useState(false);
  const [runbookState, setRunbookState] = useState('idle');
  const [runbookResult, setRunbookResult] = useState(null);
  const [gateDecision, setGateDecision] = useState(null);
  const [purposeLoading, setPurposeLoading] = useState(false);

  // Live data — capabilities/verdict can be recomputed when purpose changes
  const [liveCapabilities, setLiveCapabilities] = useState(result.capabilities || []);
  const [livePurposeVerdict, setLivePurposeVerdict] = useState(result.purpose_verdict || null);
  const [purposeSummary, setPurposeSummary] = useState('');

  // Recompute capabilities when purpose changes
  const handlePurposeChange = useCallback(async (newPurpose) => {
    setSelectedPurpose(newPurpose);
    setFlippedCard(null);

    // Skip API call if no capabilities in the result
    if (!result.capabilities?.length) return;

    setPurposeLoading(true);
    try {
      const updated = await api.recomputePurpose(result, newPurpose);
      setLiveCapabilities(updated.capabilities || []);
      setLivePurposeVerdict(updated.purpose_verdict || null);
      setPurposeSummary(updated.purpose_summary || '');
    } catch (err) {
      // Fallback: clear gaps/required if API fails
      setLiveCapabilities((result.capabilities || []).map(c => ({ ...c, required: 0, gap: false })));
      setLivePurposeVerdict(null);
      setPurposeSummary('');
    }
    setPurposeLoading(false);
  }, [result]);

  const handleRunbook = async () => {
    if (runbookState === 'loading') return;
    if (runbookResult) { setShowRunbook(true); return; }
    setRunbookState('loading');
    try {
      const res = await api.runbook(result);
      setRunbookResult(res);
      setRunbookState('ready');
      setShowRunbook(true);
    } catch { setRunbookState('idle'); }
  };

  // Use result directly as the "data" binding
  const data = result;

  if (!data?.tables?.length) {
    return (
      <section className="container py-12">
        <div className="max-w-5xl mx-auto text-center py-24">
          <p className="text-lg text-muted-foreground mb-4">No assessment data available.</p>
          <Button variant="default" onClick={onRestart}><RotateCcw className="h-4 w-4" /> New Assessment</Button>
        </div>
      </section>
    );
  }

  const assessed = data.tables.filter((t) => t.klass !== 'reference');
  const reference = data.tables.filter((t) => t.klass === 'reference');
  const hasAttestationItems = data.tables.some(
    (t) => (t.gated_by?.length ?? 0) > 0 || (t.deferred?.length ?? 0) > 0
  );

  // Derive issue count per lens from checks
  const lensIssueCount = (lensId) => {
    const ls = data.lens_scores?.find((l) => l.lens === lensId);
    return ls ? ls.check_count - ls.pass_count : 0;
  };

  // Determine which lens is "active" (matches selected purpose family)
  const activeLensId = useMemo(() => {
    if (!selectedPurpose) return null;
    for (const [lensId, families] of Object.entries(LENS_TO_FAMILIES)) {
      if (families.some((f) => selectedPurpose.startsWith(f))) return lensId;
    }
    return null;
  }, [selectedPurpose]);

  // Table filtering and sorting
  const filteredTables = useMemo(() => {
    let list = [...assessed];
    if (tableSearch) {
      const q = tableSearch.toLowerCase();
      list = list.filter((t) => t.table_name.toLowerCase().includes(q));
    }
    if (tableSort === 'worst') list.sort((a, b) => a.overall_score - b.overall_score);
    else if (tableSort === 'best') list.sort((a, b) => b.overall_score - a.overall_score);
    else if (tableSort === 'name') list.sort((a, b) => a.table_name.localeCompare(b.table_name));
    return list;
  }, [assessed, tableSearch, tableSort]);

  const selectedTable = data.tables.find((t) => t.table_name === inspectingTable);

  // Action plan grouping
  const actionGroups = data.action_groups || [];
  const mustFix = actionGroups.filter((g) => g.severity === 'blocker');
  const purposeFix = actionGroups.filter((g) => g.severity !== 'blocker' && g.score_delta > 0);
  const worthImproving = actionGroups.filter((g) => g.severity !== 'blocker' && !(g.score_delta > 0));

  return (
    <section className="container py-8">
      <div className="max-w-[1060px] mx-auto space-y-5">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b-2 border-primary pb-3 flex-wrap gap-3">
          <Button variant="ghost" size="sm" onClick={onRestart}><ArrowLeft className="h-3.5 w-3.5" /> Back</Button>
          <p className="text-[12px] text-muted-foreground font-nav">
            run {new Date().toISOString().slice(0, 10)} · reproducible (temp 0)
          </p>
        </div>

        {/* ── PURPOSE SELECTOR (top-level, always visible) ────────────── */}
        <PurposeDropdown
          selectedPurpose={selectedPurpose}
          onPurposeChange={handlePurposeChange}
          loading={purposeLoading}
        />

        {/* ── SECTION 1: Lens Flip Cards ─────────────────────────────────── */}
        {data.lens_scores?.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {data.lens_scores.map((ls) => {
              const lens = LENSES.find((l) => l.id === ls.lens) || { id: ls.lens, label: ls.label, color: '', bgColor: '' };
              const families = LENS_TO_FAMILIES[ls.lens] || [];
              const archetypes = ARCHETYPE_FAMILIES.filter((f) => families.includes(f.id));
              const issues = lensIssueCount(ls.lens);
              const isActive = activeLensId === ls.lens;

              return (
                <FlipCard
                  key={ls.lens}
                  flipped={flippedCard === ls.lens}
                  onFlip={() => setFlippedCard(flippedCard === ls.lens ? null : ls.lens)}
                  active={isActive}
                  className="min-h-[200px]"
                  front={
                    <div className="flex flex-col items-center justify-center h-full py-6 px-4 text-center">
                      <p className="font-nav text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                        {ls.label}
                      </p>
                      <p className={cn('font-display text-[48px] font-bold leading-none', SCORE_COLOR(ls.score))}>
                        {ls.score}
                      </p>
                      <p className={cn('text-[13px] font-medium mt-2', SCORE_COLOR(ls.score))}>
                        {STATUS_WORD(ls.score)}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {issues > 0 ? `${issues} issue${issues !== 1 ? 's' : ''}` : 'no issues'}
                      </p>
                      <p className="text-[10px] text-muted-foreground/60 mt-3">
                        flip to pick a purpose &#x21bb;
                      </p>
                    </div>
                  }
                  back={
                    <div className="flex flex-col h-full py-3 px-3 overflow-y-auto">
                      <p className="font-nav text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 text-center">
                        {ls.label} · purposes
                      </p>
                      <div className="space-y-2 flex-1">
                        {archetypes.map((fam) => (
                          <div key={fam.id}>
                            <p className="font-nav text-[9px] uppercase tracking-wide text-muted-foreground/60 mb-1">{fam.label}</p>
                            <div className="space-y-1">
                              {fam.archetypes?.filter(a => !a.disabled).map((arch) => (
                                <button
                                  key={arch.id}
                                  type="button"
                                  onClick={(e) => { e.stopPropagation(); handlePurposeChange(arch.id); }}
                                  className={cn(
                                    'w-full text-left px-2 py-1.5 rounded-md text-[11px] transition-colors',
                                    selectedPurpose === arch.id
                                      ? 'bg-primary/10 border border-primary font-semibold'
                                      : 'hover:bg-muted/30'
                                  )}
                                >
                                  {arch.label}
                                </button>
                              )) || null}
                              {fam.archetypes?.filter(a => a.disabled).map((arch) => (
                                <span
                                  key={arch.id}
                                  className="block w-full text-left px-2 py-1.5 rounded-md text-[11px] text-muted-foreground/40 cursor-not-allowed"
                                  title={arch.disabledReason || 'Not available'}
                                >
                                  {arch.label}
                                </span>
                              )) || null}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  }
                />
              );
            })}
          </div>
        )}

        {/* ── SECTION 2: Verdict Strip ───────────────────────────────────── */}
        <VerdictStrip data={data} gateDecision={gateDecision} onGateDecision={setGateDecision}
          liveCapabilities={liveCapabilities} livePurposeVerdict={livePurposeVerdict}
          selectedPurpose={selectedPurpose} purposeSummary={purposeSummary} />

        {/* ── SECTION 2b: Capability Fit (first section after verdict) ──── */}
        {liveCapabilities.length > 0 && (
          <CapabilitiesSection capabilities={liveCapabilities} selectedPurpose={selectedPurpose} data={data} loading={purposeLoading} />
        )}

        {/* ── SECTION 3: Tables list ─────────────────────────────────────── */}
        <CollapsibleSection title={`Tables (${assessed.length} assessed)`}>
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search tables..."
                value={tableSearch}
                onChange={(e) => setTableSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-[13px] border border-border rounded-lg bg-background font-nav"
              />
            </div>
            <select
              value={tableSort}
              onChange={(e) => setTableSort(e.target.value)}
              className="font-nav text-[12px] px-3 py-2 border border-border rounded-lg bg-background"
            >
              <option value="worst">Worst first</option>
              <option value="best">Best first</option>
              <option value="name">Name A-Z</option>
            </select>
          </div>
          <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
            {filteredTables.map((t) => {
              const issues = (t.gated_by?.length || 0) + (t.dimensions || []).reduce(
                (sum, d) => sum + (d.checks || []).filter((c) => c.status !== 'pass').length, 0
              );
              return (
                <button
                  key={t.table_name}
                  type="button"
                  onClick={() => setInspectingTable(t.table_name)}
                  className={cn(
                    'w-full text-left flex items-center gap-3 px-4 py-3 border rounded-xl transition-colors',
                    inspectingTable === t.table_name ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/20'
                  )}
                >
                  {(t.gated_by?.length > 0) && (
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-tier-red-light text-tier-red-base shrink-0">attention</span>
                  )}
                  <span className="font-mono text-[13px] flex-1 min-w-0 truncate">{t.table_name}</span>
                  <span className="text-[11px] text-muted-foreground shrink-0">{t.row_count?.toLocaleString()} rows</span>
                  <span className="text-[11px] text-muted-foreground shrink-0">{issues} issue{issues !== 1 ? 's' : ''}</span>
                  <span className={cn('font-display font-bold text-[16px] w-[36px] text-right shrink-0', SCORE_COLOR(t.overall_score))}>{t.overall_score}</span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                </button>
              );
            })}
            {reference.length > 0 && (
              <div className="pt-2 space-y-1.5">
                {reference.map((t) => (
                  <div key={t.table_name} className="flex items-center gap-3 px-4 py-2.5 border border-border rounded-xl opacity-50">
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">excluded · reference</span>
                    <span className="font-mono text-[13px] flex-1 min-w-0 truncate">{t.table_name}</span>
                    <span className="text-[11px] text-muted-foreground">{t.excluded_reason || 'reference'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CollapsibleSection>

        {/* ── SECTION 4: Table Detail ────────────────────────────────────── */}
        {selectedTable && (
          <Card className="surface-vignette-subtle"><CardContent className="p-6">
            <TableDetail
              table={selectedTable}
              onClose={() => setInspectingTable('')}
            />
          </CardContent></Card>
        )}

        {/* ── SECTION 5: Metadata Quality ────────────────────────────────── */}
        {data.metadata_quality && (
          <MetadataSection data={data} onSelectTable={setInspectingTable} />
        )}

        {/* ── SECTION 6: Action Plan ─────────────────────────────────────── */}
        <CollapsibleSection title="Action Plan">
          <div className="flex justify-end gap-2 mb-4">
            <Button variant="outline" size="sm" onClick={handleRunbook} disabled={runbookState === 'loading'}>
              {runbookState === 'loading' ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Generating...</> :
               runbookState === 'ready' ? <><CheckCircle2 className="h-3.5 w-3.5 text-tier-green-base" /> View engineer playbook</> :
               <><RotateCcw className="h-3.5 w-3.5" /> View engineer playbook</>}
            </Button>
            <DownloadMdButton data={data} />
          </div>
          <div className="space-y-4 max-h-[700px] overflow-y-auto">
            {mustFix.length > 0 && (
              <ActionTier label={`MUST FIX — GATES (${mustFix.length})`} items={mustFix} variant="blocker" />
            )}
            {purposeFix.length > 0 && (
              <ActionTier label={`FIX FOR THIS PURPOSE (${purposeFix.length})`} items={purposeFix} variant="warning" />
            )}
            {worthImproving.length > 0 && (
              <ActionTier label={`WORTH IMPROVING (${worthImproving.length})`} items={worthImproving} variant="info" />
            )}
          </div>
        </CollapsibleSection>

        {/* ── SECTION 8: Attestation Queue ───────────────────────────────── */}
        {hasAttestationItems && (
          <AttestationQueue
            tables={data.tables}
            result={data}
            onRescore={onRescore}
            onGateDecision={setGateDecision}
          />
        )}

        {showRunbook && <RunbookModal result={runbookResult} onClose={() => setShowRunbook(false)} />}
      </div>
    </section>
  );
}

// ─── SECTION 2: Verdict Strip ────────────────────────────────────────────────
function VerdictStrip({ data, gateDecision, onGateDecision, liveCapabilities, livePurposeVerdict, selectedPurpose, purposeSummary }) {
  const tier = data.tier || tierFor(data.overall_score);
  const gatedCount = data.gated_by?.length || 0;
  const gapCount = liveCapabilities?.filter((c) => c.gap).length || 0;
  const defaultNarrative = data.tables?.[0]?.narrative || data.narrative || '';

  // Use purpose summary when available, fallback to per-table narrative
  const narrative = purposeSummary || defaultNarrative;

  // Use purpose verdict label when available
  const verdictLabel = livePurposeVerdict?.verdict ||
    data.verdict || (tier === 'green' ? 'AI Ready' : tier === 'yellow' ? 'Conditional' : 'At Risk');

  const bannerBg = tier === 'red' ? 'bg-tier-red-light border-tier-red-base/30' :
    tier === 'yellow' ? 'bg-tier-amber-light border-tier-amber-base/30' :
    'bg-tier-green-light border-tier-green-base/30';
  const bannerText = tier === 'red' ? 'text-tier-red-base' :
    tier === 'yellow' ? 'text-tier-amber-base' : 'text-tier-green-base';

  // Derive purpose label
  const purposeLabel = selectedPurpose
    ? ARCHETYPE_FAMILIES.flatMap(f => f.archetypes || []).find(a => a.id === selectedPurpose)?.label
    : null;

  return (
    <div className={cn('rounded-xl border p-4', bannerBg)}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className={cn('font-nav text-[12px] font-bold uppercase tracking-wide', bannerText)}>
          {verdictLabel}
        </span>
        {purposeLabel && (
          <>
            <span className="text-[11px] text-muted-foreground">·</span>
            <span className="text-[11px] text-muted-foreground font-medium">for {purposeLabel}</span>
          </>
        )}
        <span className="text-[11px] text-muted-foreground">·</span>
        <span className="text-[11px] text-muted-foreground font-medium">{gatedCount} gated</span>
        <span className="text-[11px] text-muted-foreground">·</span>
        <span className="text-[11px] text-muted-foreground font-medium">{gapCount} capability gap{gapCount !== 1 ? 's' : ''}</span>
        <span className={cn('ml-auto font-display text-[28px] font-bold', SCORE_COLOR(data.overall_score))}>{data.overall_score}</span>
      </div>
      {narrative && (
        <p className="text-[13px] text-foreground/80 mt-3 leading-relaxed">{narrative}</p>
      )}
      <div className="flex gap-2 mt-3">
        {gatedCount > 0 && (
          <button
            type="button"
            onClick={() => document.getElementById('attestation-queue')?.scrollIntoView({ behavior: 'smooth' })}
            className="text-[11px] font-bold uppercase px-3 py-1.5 rounded-lg bg-tier-red-light text-tier-red-base border border-tier-red-base/20 hover:bg-tier-red-light/70 transition-colors"
          >
            tables gated {gatedCount}/{data.tables?.length || 0} &gt;
          </button>
        )}
        {gapCount > 0 && (
          <button
            type="button"
            onClick={() => document.getElementById('capabilities-ref')?.scrollIntoView({ behavior: 'smooth' })}
            className="text-[11px] font-bold uppercase px-3 py-1.5 rounded-lg bg-tier-amber-light text-tier-amber-base border border-tier-amber-base/20 hover:bg-tier-amber-light/70 transition-colors"
          >
            capability gaps {gapCount} &gt;
          </button>
        )}
      </div>
      {/* Gate decision banners */}
      {gatedCount > 0 && gateDecision === 'acknowledged' && (
        <p className="text-[12px] text-tier-green-base mt-3 font-medium">
          Remediation acknowledged. Governed score stays at {data.overall_score} until resolved.
        </p>
      )}
      {gatedCount > 0 && gateDecision === 'accepted_risk' && (
        <p className="text-[12px] text-tier-amber-base mt-3 font-medium">
          Governance override recorded. Blocker flag preserved.
        </p>
      )}
    </div>
  );
}

// ─── SECTION 5: Metadata Quality (4-category) ──────────────────────────────
function MetadataSection({ data, onSelectTable }) {
  const mq = data.metadata_quality;
  if (!mq) return null;

  const [expandedCat, setExpandedCat] = useState(null);

  // BOTL categories
  const BOTL_COLORS = {
    business: 'bg-blue-500',
    operational: 'bg-tier-amber-base',
    technical: 'bg-primary',
    lineage: 'bg-tier-green-base',
  };

  const categories = mq.categories || [];
  const remediation = mq.remediation || [];
  const verdict = mq.verdict || 'RED';
  const overallPct = Math.round((mq.scores?.overall ?? 0) * 100);

  const verdictConfig = {
    RED: { bg: 'bg-tier-red-light border-tier-red-base/30', text: 'text-tier-red-base', label: 'At Risk — HIGH-severity fields missing or invalid' },
    YELLOW: { bg: 'bg-tier-amber-light border-tier-amber-base/30', text: 'text-tier-amber-base', label: 'Conditional — MEDIUM-severity fields incomplete' },
    GREEN: { bg: 'bg-tier-green-light border-tier-green-base/30', text: 'text-tier-green-base', label: 'Documented — all required metadata present and valid' },
  };
  const vc = verdictConfig[verdict] || verdictConfig.RED;

  const sevColor = (sev) => sev === 'HIGH' ? 'bg-tier-red-light text-tier-red-base' : sev === 'MEDIUM' ? 'bg-tier-amber-light text-tier-amber-base' : 'bg-muted text-muted-foreground';

  return (
    <CollapsibleSection title="Metadata Quality" subtitle={`UMS v2.0 BOTL · ${verdict}`} defaultOpen>
      {/* Verdict banner */}
      <div className={cn('rounded-xl border p-3 mb-4', vc.bg)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={cn('font-nav text-[11px] font-bold uppercase tracking-wide', vc.text)}>{verdict}</span>
            <span className="text-[12px] text-foreground/70">{vc.label}</span>
          </div>
          <span className={cn('font-display font-bold text-[22px]', SCORE_COLOR(overallPct))}>{overallPct}%</span>
        </div>
      </div>

      {/* 4-category cards (B · O · T · L) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {categories.map((cat) => {
          const color = BOTL_COLORS[cat.category] || 'bg-muted';
          const isExpanded = expandedCat === cat.category;
          const catFields = (mq.fields || []).filter(f => f.category === cat.category);
          return (
            <div key={cat.category} className="border border-border rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="font-nav text-[11px] font-semibold uppercase tracking-wide capitalize">{cat.category}</span>
                <span className="text-[10px] text-muted-foreground">{cat.fields_valid}/{cat.fields_total} valid</span>
              </div>
              <div className="flex items-end gap-2 mb-2">
                <span className={cn('font-display font-bold text-[22px]', SCORE_COLOR(cat.score_pct))}>
                  {cat.score_pct}%
                </span>
              </div>
              <div className="h-1.5 bg-border rounded-full overflow-hidden mb-2">
                <div className={cn('h-full rounded-full', color)} style={{ width: `${cat.score_pct}%` }} />
              </div>
              <div className="text-[10px] text-muted-foreground">
                {cat.points_earned}/{cat.points_possible} pts
              </div>
              {/* Expand toggle */}
              {catFields.length > 0 && (
                <button
                  type="button"
                  onClick={() => setExpandedCat(isExpanded ? null : cat.category)}
                  className="text-[10px] text-primary mt-2 hover:underline"
                >
                  {isExpanded ? 'hide fields' : `show ${catFields.length} fields`}
                </button>
              )}
              {isExpanded && (
                <div className="mt-2 space-y-1 border-t border-border/40 pt-2">
                  {catFields.map((f) => (
                    <div key={f.field_id} className="flex items-center gap-1.5 text-[10px]">
                      {f.valid ? (
                        <span className="w-1.5 h-1.5 rounded-full bg-tier-green-base shrink-0" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-tier-red-base shrink-0" />
                      )}
                      <span className="text-muted-foreground font-mono">{f.field_id}</span>
                      <span className={f.valid ? 'text-foreground/70' : 'text-foreground'}>{f.field_name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Remediation Recommendations */}
      {remediation.length > 0 && (
        <div>
          <p className="font-nav text-[10px] uppercase tracking-wide text-muted-foreground font-semibold mb-3">
            Remediation Recommendations ({remediation.length})
          </p>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {remediation.slice(0, 15).map((r) => (
              <div key={r.field_id} className="border border-border rounded-xl px-4 py-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-bold text-muted-foreground w-[24px] shrink-0">#{r.priority}</span>
                  <span className={cn('text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0', sevColor(r.effective_severity))}>
                    {r.effective_severity}
                  </span>
                  <span className="font-mono text-[11px] text-primary shrink-0">{r.field_id}</span>
                  <span className="text-[12px] font-medium flex-1 truncate">{r.field_name}</span>
                  <span className="text-[10px] font-bold text-tier-green-base shrink-0">+{r.points_recoverable} pts</span>
                </div>
                <div className="pl-[24px] space-y-1">
                  <p className="text-[11px] text-foreground/80">
                    <span className="font-semibold">Gap:</span> {r.reason}
                  </p>
                  {r.why && (
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      <span className="font-semibold">Why:</span> {r.why.length > 200 ? r.why.slice(0, 200) + '...' : r.why}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground">
                    <span className="font-medium">Owner:</span> {r.owner_route === 'business' ? 'Business owner' : 'Platform team'}
                  </p>
                </div>
              </div>
            ))}
            {remediation.length > 15 && (
              <p className="text-[11px] text-muted-foreground text-center py-2">
                + {remediation.length - 15} more items. Upload a data dictionary to reduce this list.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Findings summary */}
      {mq.findings?.length > 0 && (
        <div className="mt-3 space-y-1">
          {mq.findings.map((f, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-muted-foreground">
              <span className="text-tier-amber-base mt-0.5 shrink-0">&#x25CF;</span>
              <span>{f}</span>
            </div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}

// ─── SECTION 5: Table Detail ─────────────────────────────────────────────────
function TableDetail({ table, onClose }) {
  const [expandedDims, setExpandedDims] = useState({});
  const [showPassChecks, setShowPassChecks] = useState(false);

  if (table.klass === 'reference') {
    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display text-lg font-bold">{table.table_name}</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
        <p className="text-[13px] text-muted-foreground">Excluded. {table.excluded_reason || 'Reference/static table, not scored.'}</p>
      </div>
    );
  }

  const dimensions = table.dimensions || [];
  const allChecks = dimensions.flatMap((d) => (d.checks || []).map((c) => ({ ...c, dimension: d.label || d.id })));
  const nonPassFieldIssues = (table.field_issues || []).filter((fi) => fi.severity !== 'info');
  const cleanFields = (table.field_issues || []).filter((fi) => fi.severity === 'info' || !fi.severity);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <div>
            <span className={cn('font-display text-[36px] font-bold', SCORE_COLOR(table.overall_score))}>{table.overall_score}</span>
          </div>
          <div>
            <h3 className="font-display text-lg font-bold">{table.table_name}</h3>
            <p className="text-[12px] text-muted-foreground">
              {table.row_count?.toLocaleString()} rows · {table.column_count || '—'} fields
              {table.gated_by?.length > 0 && <span className="ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-tier-red-light text-tier-red-base">gated</span>}
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>

      {/* AI narrative */}
      {table.narrative && (
        <div className="bg-muted/20 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-violet-600 text-white">AI</span>
            <span className="text-[11px] text-muted-foreground">advisory narrative</span>
          </div>
          <p className="text-[13px] text-foreground/85 leading-relaxed">{table.narrative}</p>
        </div>
      )}

      {/* Dimensions */}
      <h4 className="font-nav text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2 mt-4">Dimensions</h4>
      <div className="space-y-1.5">
        {dimensions.map((dim) => {
          const passCount = (dim.checks || []).filter((c) => c.status === 'pass').length;
          const totalChecks = (dim.checks || []).length;
          const dimScore = dim.score ?? (table.dimension_scores?.[dim.id]);
          const isExpanded = expandedDims[dim.id];

          return (
            <div key={dim.id} className="border border-border rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => setExpandedDims((p) => ({ ...p, [dim.id]: !p[dim.id] }))}
                className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-muted/20 transition-colors"
              >
                <ChevronRight className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', isExpanded && 'rotate-90')} />
                <span className="flex-1 text-[13px] font-medium">{dim.label || dim.id}</span>
                <span className="text-[11px] text-muted-foreground">{passCount}/{totalChecks}</span>
                <div className="w-[80px] h-2 bg-border rounded-full overflow-hidden">
                  {dimScore != null && <div className={cn('h-full rounded-full', BAR_COLOR(dimScore))} style={{ width: `${dimScore}%` }} />}
                </div>
                <span className={cn('font-display font-bold text-[15px] w-[32px] text-right', dimScore != null ? SCORE_COLOR(dimScore) : 'text-muted-foreground')}>
                  {dimScore ?? 'N/A'}
                </span>
              </button>
              {isExpanded && (
                <div className="px-4 pb-3 pt-1 border-t border-border/40 bg-muted/10 space-y-1">
                  {(dim.checks || []).filter((c) => c.status !== 'pass').map((c) => (
                    <div key={c.rule_id} className="flex items-baseline gap-2 text-[12px] py-1">
                      <a href={`#action-${c.rule_id}`} className={cn(
                        'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0 hover:opacity-80',
                        c.severity === 'blocker' ? SEV_COLORS.blocker :
                        c.status === 'fail' ? SEV_COLORS.blocker :
                        c.status === 'warn' ? SEV_COLORS.warning : SEV_COLORS.info
                      )}>
                        {c.severity === 'blocker' ? 'BLOCKER' : c.status === 'fail' ? 'FAIL' : 'WARN'}
                      </a>
                      <span className="text-foreground/80">{c.title} — {c.detail}</span>
                    </div>
                  ))}
                  {passCount > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowPassChecks(!showPassChecks)}
                      className="text-[11px] text-muted-foreground hover:text-foreground mt-1"
                    >
                      {passCount} checks passed — {showPassChecks ? 'hide' : 'show what was verified'}
                    </button>
                  )}
                  {showPassChecks && (dim.checks || []).filter((c) => c.status === 'pass').map((c) => (
                    <div key={c.rule_id} className="flex items-baseline gap-2 text-[11px] py-0.5 text-muted-foreground">
                      <span className="text-tier-green-base font-bold w-[12px]">&#x2713;</span>
                      <span>{c.title}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Column Insights */}
      {nonPassFieldIssues.length > 0 && (
        <div className="mt-5">
          <h4 className="font-nav text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Column Insights</h4>
          <p className="text-[11px] text-muted-foreground mb-3">only fields that need something — healthy fields are listed by name, not described</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] min-w-[500px]">
              <thead><tr className="border-b">
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left">Field</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left">What we found</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left">What to do</th>
              </tr></thead>
              <tbody>
                {nonPassFieldIssues.map((fi, i) => {
                  // Find the originating check to get its detail (the observation)
                  const sourceCheck = allChecks.find((c) => c.evidence?.candidates?.includes(fi.field) || c.evidence?.column === fi.field || c.evidence?.columns?.includes(fi.field));
                  const whatFound = sourceCheck?.detail || fi.issue;
                  const whatToDo = sourceCheck?.recommendation || fi.issue;
                  return (
                    <tr key={i} className="border-b border-border/30">
                      <td className="py-2 font-mono text-[11px] text-primary">{fi.field}</td>
                      <td className="py-2 text-muted-foreground">{whatFound}</td>
                      <td className="py-2">{whatToDo !== whatFound ? whatToDo : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {cleanFields.length > 0 && (
            <p className="text-[11px] text-muted-foreground mt-2">
              Clean ({cleanFields.length}): {cleanFields.map((f) => f.field).join(', ')}
            </p>
          )}
        </div>
      )}

      {/* All Checks table */}
      {allChecks.length > 0 && (
        <div className="mt-5">
          <h4 className="font-nav text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">All Checks</h4>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-[12px] min-w-[800px]">
              <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10"><tr className="border-b">
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[14%]">Area</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[18%]">Check</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[28%]">Result</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[14%]">Expected</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[16%]">How Measured</th>
                <th className="pb-1.5 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-center w-[10%]">Status</th>
              </tr></thead>
              <tbody>
                {allChecks.map((c) => {
                  const basisLabels = { exact: 'exact', sample: 'sample', pushdown: 'pushdown', dictionary: 'dictionary', language_model: 'language model', association: 'association' };
                  const basisLabel = basisLabels[c.basis] || c.basis || '—';
                  const rows = table.profiled_row_count || table.row_count;
                  const howMeasured = c.basis === 'exact' && rows
                    ? `${basisLabel} · full scan (${rows.toLocaleString()} rows)`
                    : c.basis === 'sample' && rows
                    ? `${basisLabel} (${rows.toLocaleString()} rows)`
                    : basisLabel;
                  return (
                  <tr key={c.rule_id} className="border-b border-border/30">
                    <td className="py-2 text-muted-foreground capitalize">{c.dimension}</td>
                    <td className="py-2 font-medium">{c.title}</td>
                    <td className="py-2 text-muted-foreground">{c.enriched_detail || c.detail || '—'}</td>
                    <td className="py-2 text-muted-foreground">{c.expected || '—'}</td>
                    <td className="py-2 text-muted-foreground text-[11px]">{howMeasured}</td>
                    <td className="py-2 text-center">
                      {c.status === 'pass' ? (
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-tier-green-light text-tier-green-base">pass</span>
                      ) : (
                        <a href={`#action-${c.rule_id}`} className={cn(
                          'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded hover:opacity-80',
                          c.severity === 'blocker' ? SEV_COLORS.blocker :
                          c.status === 'fail' ? SEV_COLORS.blocker : SEV_COLORS.warning
                        )}>
                          {c.severity === 'blocker' ? 'BLOCKER' : c.status}
                        </a>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── SECTION 6: Action Tier ──────────────────────────────────────────────────
function ActionTier({ label, items, variant }) {
  const [open, setOpen] = useState(true);
  const labelColor = variant === 'blocker' ? 'text-tier-red-base' : variant === 'warning' ? 'text-tier-amber-base' : 'text-muted-foreground';

  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-2 mb-2 w-full text-left">
        <ChevronDown className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform duration-200', !open && '-rotate-90')} />
        <span className={cn('text-[12px] font-bold uppercase tracking-wide', labelColor)}>{label}</span>
      </button>
      {open && items.map((g) => <ActionCard key={g.rule_id} group={g} isBlocker={variant === 'blocker'} />)}
    </div>
  );
}

function ActionCard({ group, isBlocker }) {
  const g = group;
  const [showExplainer, setShowExplainer] = useState(false);
  const details = g.table_details || [];

  return (
    <div id={`action-${g.rule_id}`} className="border border-border rounded-xl mb-3 overflow-hidden scroll-mt-20">
      <div className="px-4 py-3 flex items-center gap-3 bg-muted/10">
        <span className={cn('text-[10px] font-bold uppercase px-2 py-0.5 rounded shrink-0', SEV_COLORS[g.severity] || SEV_COLORS.info)}>{g.severity}</span>
        <span className="font-semibold text-[13.5px] flex-1">{g.issue}</span>
        {g.score_delta > 0 && <span className="text-[10px] font-bold text-tier-green-base bg-tier-green-light px-2 py-0.5 rounded shrink-0">+{g.score_delta} pts</span>}
      </div>
      <div className="px-4 pb-4 border-t border-border/40 bg-muted/10 pt-3 space-y-2">
        {details.length > 0 ? (
          <div className="space-y-1.5">
            {details.map((td, i) => (
              <div key={i} className="flex items-start gap-2 text-[12px]">
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">{td.table_name}</span>
                <span className="text-foreground/80">{td.detail}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {g.affected_tables?.map((t) => <span key={t} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{t}</span>)}
          </div>
        )}
        {g.recommended_fix && (
          <p className="text-[12px] text-foreground/85"><span className="font-semibold">now:</span> {g.recommended_fix}</p>
        )}
        {g.explanation && (
          <button type="button" onClick={() => setShowExplainer(!showExplainer)} className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1">
            <ChevronDown className={cn('h-3 w-3 transition-transform duration-150', !showExplainer && '-rotate-90')} />
            {showExplainer ? 'hide context' : 'why this matters'}
          </button>
        )}
        {showExplainer && g.explanation && (
          <p className="text-[11px] text-muted-foreground pl-4 border-l-2 border-border">{g.explanation.what} {g.explanation.why}</p>
        )}
        {g.basis && (
          <p className="text-[11px] text-muted-foreground"><span className="font-medium">measured:</span> {g.basis}</p>
        )}
        {isBlocker && (
          <a href="#attestation-queue" className="text-[10px] text-tier-amber-base hover:underline block mt-1">
            accept this risk in Human attestation &#x2193;
          </a>
        )}
      </div>
    </div>
  );
}

// ─── SECTION 7: Capabilities Reference ───────────────────────────────────────
function CapabilitiesSection({ capabilities, selectedPurpose, data, loading }) {
  const capDefs = CAPABILITIES;
  const purposeLabel = selectedPurpose
    ? ARCHETYPE_FAMILIES.flatMap(f => f.archetypes || []).find(a => a.id === selectedPurpose)?.label || selectedPurpose
    : null;

  // Find checks linked to a capability's evidence (both pass and non-pass)
  const findRelatedChecks = (cap) => {
    if (!cap.evidence?.length || !data?.tables?.length) return [];
    const checks = [];
    for (const table of data.tables) {
      if (!table.included) continue;
      for (const dim of (table.dimensions || [])) {
        for (const c of (dim.checks || [])) {
          if (c.status === 'deferred') continue;
          if (cap.evidence.includes(c.finding_uid)) {
            checks.push({ ...c, table_name: table.table_name });
          }
        }
      }
    }
    return checks;
  };

  const gaps = capabilities.filter(c => c.gap);

  // Sort: required capabilities first (relevant to selected purpose), then by level desc
  const sorted = [...capabilities].sort((a, b) => {
    const aRelevant = a.required > 0 ? 0 : 1;
    const bRelevant = b.required > 0 ? 0 : 1;
    if (aRelevant !== bRelevant) return aRelevant - bRelevant;
    return b.level - a.level;
  });

  // When a purpose is selected, split into relevant (shown) and other (folded)
  const relevant = selectedPurpose ? sorted.filter(c => c.required > 0) : sorted;
  const other = selectedPurpose ? sorted.filter(c => c.required === 0) : [];
  const [showOther, setShowOther] = useState(false);

  return (
    <CollapsibleSection
      title="Capability fit"
      subtitle={purposeLabel ? `measured vs required for ${purposeLabel}` : 'no purpose selected — showing measured levels'}
      defaultOpen={gaps.length > 0 || capabilities.length > 0}
    >
      {loading && (
        <div className="flex items-center gap-2 mb-3 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Recomputing for new purpose...
        </div>
      )}
      <div id="capabilities-ref" className="overflow-x-auto">
        <table className="w-full text-[12.5px] min-w-[700px]">
          <thead><tr className="border-b">
            <th className="pb-2 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[22%]">Capability</th>
            <th className="pb-2 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[22%]">Measured</th>
            <th className="pb-2 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-center w-[12%]">Status</th>
            <th className="pb-2 text-[10px] uppercase text-muted-foreground font-semibold tracking-wide text-left w-[44%]">Evidence</th>
          </tr></thead>
          <tbody>
            {relevant.map((cap) => {
              const def = capDefs.find(d => d.id === cap.id);
              const measuredLabel = LEVEL_LABELS[cap.level] || LEVEL_LABELS[0];
              const isGap = cap.gap;
              const isRelevant = cap.required > 0;
              const gapDelta = isGap ? cap.required - cap.level : 0;
              const status = isGap ? `GAP -${gapDelta}` : isRelevant ? 'MET' : '';
              const statusColor = isGap ? 'text-tier-red-base bg-tier-red-light' :
                isRelevant ? 'text-tier-green-base bg-tier-green-light' :
                'text-muted-foreground bg-transparent';
              const relatedChecks = findRelatedChecks(cap);

              return (
                <tr key={cap.id} className="border-b border-border/30 align-top">
                  <td className="py-3">
                    <CapabilityLabel label={cap.label || def?.label} definition={def?.definition} />
                  </td>
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <CapDots level={cap.level} max={4} isWeak={cap.level <= 1} />
                      <span className="text-muted-foreground text-[11px]">
                        {measuredLabel}
                        {isRelevant && ` (need ${LEVEL_LABELS[cap.required] || 'solid'})`}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 text-center">
                    {status && (
                      <span className={cn('text-[10px] font-bold uppercase px-2 py-0.5 rounded', statusColor)}>
                        {status}
                      </span>
                    )}
                  </td>
                  <td className="py-3 text-[11px] text-muted-foreground">
                    {relatedChecks.length > 0 ? (
                      <div className="space-y-1">
                        {relatedChecks.slice(0, 4).map((c, i) => (
                          <div key={i} className="flex items-start gap-2">
                            {c.status === 'pass' ? (
                              <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded bg-tier-green-light text-tier-green-base shrink-0">PASS</span>
                            ) : (
                              <span className={cn('text-[9px] font-bold uppercase px-1 py-0.5 rounded shrink-0',
                                c.severity === 'blocker' ? 'bg-tier-red-base text-white' :
                                c.status === 'fail' ? SEV_COLORS.blocker : SEV_COLORS.warning
                              )}>{c.severity === 'blocker' ? 'BLOCKER' : c.status?.toUpperCase()}</span>
                            )}
                            <div className="flex-1">
                              <span className={c.status === 'pass' ? 'text-foreground/60' : 'text-foreground/80'}>
                                {c.enriched_detail || c.detail || c.title}
                              </span>
                              {c.table_name && (
                                <span className="ml-1 text-[10px] text-muted-foreground">({c.table_name})</span>
                              )}
                            </div>
                          </div>
                        ))}
                        {relatedChecks.length > 4 && (
                          <span className="text-[10px] text-muted-foreground">+{relatedChecks.length - 4} more</span>
                        )}
                      </div>
                    ) : isGap ? (
                      <span className="italic">capability below required floor</span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
          {showOther && other.length > 0 && (
            <tbody className="opacity-40">
              {other.map((cap) => {
                const def = capDefs.find(d => d.id === cap.id);
                const measuredLabel = LEVEL_LABELS[cap.level] || LEVEL_LABELS[0];
                const relatedChecks = findRelatedChecks(cap);
                return (
                  <tr key={cap.id} className="border-b border-border/30 align-top">
                    <td className="py-3">
                      <CapabilityLabel label={cap.label || def?.label} definition={def?.definition} />
                    </td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <CapDots level={cap.level} max={4} isWeak={cap.level <= 1} />
                        <span className="text-muted-foreground text-[11px]">{measuredLabel}</span>
                      </div>
                    </td>
                    <td className="py-3 text-center" />
                    <td className="py-3 text-[11px] text-muted-foreground">
                      {relatedChecks.length > 0 ? (
                        <div className="space-y-1">
                          {relatedChecks.slice(0, 2).map((c, i) => (
                            <div key={i} className="flex items-start gap-2">
                              {c.status === 'pass' ? (
                                <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded bg-tier-green-light text-tier-green-base shrink-0">PASS</span>
                              ) : (
                                <span className={cn('text-[9px] font-bold uppercase px-1 py-0.5 rounded shrink-0',
                                  c.status === 'fail' ? SEV_COLORS.blocker : SEV_COLORS.warning
                                )}>{c.status?.toUpperCase()}</span>
                              )}
                              <span className="text-foreground/50">{c.enriched_detail || c.detail || c.title}</span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          )}
        </table>
        {selectedPurpose && other.length > 0 && (
          <button
            type="button"
            onClick={() => setShowOther(!showOther)}
            className="text-[11px] text-muted-foreground hover:text-foreground mt-2 flex items-center gap-1"
          >
            <ChevronDown className={cn('h-3 w-3 transition-transform', !showOther && '-rotate-90')} />
            {showOther ? 'Hide' : 'Show'} {other.length} more capabilities
          </button>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground mt-3">
        scale: unknown · weak · partial · solid · verified · hover a capability name for what it measures
      </p>
    </CollapsibleSection>
  );
}

// Tooltip-enabled capability label
function CapabilityLabel({ label, definition }) {
  const [showTip, setShowTip] = useState(false);
  return (
    <span
      className="relative inline-flex items-center gap-1 group"
      onMouseEnter={() => setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
    >
      <span className="font-medium cursor-help">{label}</span>
      <Info className="h-3 w-3 text-muted-foreground/50 shrink-0" />
      {showTip && definition && (
        <span className="absolute z-50 left-0 top-full mt-1.5 w-[220px] px-3 py-2 rounded-lg bg-foreground text-background text-[11px] leading-snug shadow-lg pointer-events-none">
          {definition}
        </span>
      )}
    </span>
  );
}

function CapDots({ level, max = 4, isWeak = false }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: max }, (_, i) => (
        <div
          key={i}
          className={cn(
            'w-2.5 h-2.5 rounded-sm',
            i < level
              ? (isWeak && i === 0 ? 'bg-tier-red-base' : 'bg-tier-green-base')
              : 'bg-border'
          )}
        />
      ))}
    </div>
  );
}

// ─── SECTION 8: Attestation Queue ────────────────────────────────────────────
function AttestationQueue({ tables, result, onRescore, onGateDecision }) {
  const DISMISSIBLE_IDS = new Set(['temporal_ordering', 'temporal_granularity', 'stats_no_constants', 'labels_balance', 'features_cardinality']);

  const deferred = (tables || []).flatMap((t) =>
    (t.deferred || []).map((c) => ({ ...c, table_name: t.table_name }))
  );
  const gated = (tables || []).flatMap((t) =>
    (t.gated_by || []).map((ruleId) => {
      const check = t.dimensions?.flatMap((d) => d.checks).find((c) => c.rule_id === ruleId);
      return check ? { ...check, table_name: t.table_name } : null;
    }).filter(Boolean)
  );
  const dismissible = (tables || []).flatMap((t) =>
    (t.dimensions || []).flatMap((d) => d.checks || [])
      .filter((c) => DISMISSIBLE_IDS.has(c.rule_id) && c.status !== 'pass' && c.status !== 'deferred')
      .map((c) => ({ ...c, table_name: t.table_name }))
  );

  const [decisions, setDecisions] = useState({});
  const [open, setOpen] = useState(true);
  const [rescoring, setRescoring] = useState(false);
  const [rescoreError, setRescoreError] = useState(null);

  if (!deferred.length && !gated.length && !dismissible.length) return null;

  const approvedRuleIds = [...new Set(
    deferred
      .filter((c) => { const d = decisions[`${c.rule_id}-${c.table_name}`]; return d === 'PII = No' || d === 'Approved'; })
      .map((c) => c.rule_id)
  )];
  const acknowledgedBlockerIds = [...new Set(
    gated
      .filter((c) => { const d = decisions[`gated-${c.rule_id}-${c.table_name}`]; return d === 'Accepted risk' || d === 'Acknowledged'; })
      .map((c) => c.rule_id)
  )];
  const dismissedRuleIds = [...new Set(
    dismissible
      .filter((c) => decisions[`dismiss-${c.rule_id}-${c.table_name}`] === 'Dismissed')
      .map((c) => c.rule_id)
  )];

  const hasDecisions = Object.keys(decisions).length > 0;
  const hasActionable = approvedRuleIds.length > 0 || acknowledgedBlockerIds.length > 0 || dismissedRuleIds.length > 0;

  const handleApplyDecisions = async () => {
    if (!hasActionable || !onRescore) return;
    setRescoring(true);
    setRescoreError(null);
    try {
      const rescored = await api.rescore(result, approvedRuleIds, acknowledgedBlockerIds, dismissedRuleIds);
      onRescore(rescored);
    } catch (err) { setRescoreError(err.message || 'Rescore failed'); }
    setRescoring(false);
  };

  return (
    <Card id="attestation-queue" className="surface-vignette-subtle"><CardContent className="p-6">
      <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-2 w-full text-left mb-1">
        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform duration-200', !open && '-rotate-90')} />
        <h2 className="font-display text-lg font-bold">Attestation Queue</h2>
      </button>
      <p className="text-[12.5px] text-muted-foreground mb-4 pl-6">
        Blocker rules, derived governance values, and dismissible findings require human confirmation.
      </p>
      {open && (
        <div className="space-y-3">
          {gated.length > 0 && (
            <AttestGroup title={`Blocker decisions (${gated.length})`}
              onApproveAll={() => { const next = {...decisions}; gated.forEach((c) => { next[`gated-${c.rule_id}-${c.table_name}`] = 'Acknowledged'; }); setDecisions(next); onGateDecision?.('acknowledged'); }}
              onRestrictAll={() => { const next = {...decisions}; gated.forEach((c) => { next[`gated-${c.rule_id}-${c.table_name}`] = 'Accepted risk'; }); setDecisions(next); onGateDecision?.('accepted_risk'); }}
            >
              {gated.map((c) => {
                const key = `gated-${c.rule_id}-${c.table_name}`;
                const decided = decisions[key];
                return (
                  <div key={key} className="flex items-center justify-between gap-3 border border-tier-red-base/30 bg-tier-red-light/30 rounded-lg px-4 py-2.5">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-tier-red-light text-tier-red-base shrink-0">blocker</span>
                      <span className="text-[13px] truncate"><b>{c.title}</b> on <code className="bg-muted px-1 rounded text-[11px]">{c.table_name}</code></span>
                    </div>
                    {decided ? (
                      <span className="text-[11px] text-tier-green-base font-semibold shrink-0">{decided}</span>
                    ) : (
                      <div className="flex items-center gap-1 shrink-0">
                        <button type="button" onClick={() => { setDecisions((p) => ({...p, [key]: 'Acknowledged'})); onGateDecision?.('acknowledged'); }} title="Acknowledge" className="p-1.5 rounded-md hover:bg-tier-green-light text-muted-foreground hover:text-tier-green-base transition-colors"><CheckCircle2 className="h-4 w-4" /></button>
                        <button type="button" onClick={() => { setDecisions((p) => ({...p, [key]: 'Accepted risk'})); onGateDecision?.('accepted_risk'); }} title="Accept risk" className="p-1.5 rounded-md hover:bg-tier-amber-light text-muted-foreground hover:text-tier-amber-base transition-colors"><ShieldAlert className="h-4 w-4" /></button>
                      </div>
                    )}
                  </div>
                );
              })}
            </AttestGroup>
          )}

          {deferred.length > 0 && (
            <AttestGroup title={`Human confirmations (${deferred.length})`}
              onApproveAll={() => { const next = {...decisions}; deferred.forEach((c) => { next[`${c.rule_id}-${c.table_name}`] = c.rule_id.includes('pii') ? 'PII = No' : 'Approved'; }); setDecisions(next); }}
              onRestrictAll={() => { const next = {...decisions}; deferred.forEach((c) => { next[`${c.rule_id}-${c.table_name}`] = c.rule_id.includes('pii') ? 'PII = Yes' : 'Restricted'; }); setDecisions(next); }}
            >
              {deferred.map((c) => {
                const key = `${c.rule_id}-${c.table_name}`;
                const decided = decisions[key];
                return (
                  <div key={key} className="flex items-center justify-between gap-3 border border-border rounded-lg px-4 py-2.5">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-blue-100 text-blue-700 shrink-0">confirm</span>
                      <span className="text-[13px] truncate"><b>{c.title}</b> on <code className="bg-muted px-1 rounded text-[11px]">{c.table_name}</code></span>
                    </div>
                    {decided ? (
                      <span className="text-[11px] text-tier-green-base font-semibold shrink-0">{decided}</span>
                    ) : (
                      <div className="flex items-center gap-1 shrink-0">
                        {c.rule_id.includes('pii') ? (
                          <>
                            <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'PII = No'}))} title="PII = No" className="p-1.5 rounded-md hover:bg-tier-green-light text-muted-foreground hover:text-tier-green-base transition-colors"><CheckCircle2 className="h-4 w-4" /></button>
                            <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'PII = Yes'}))} title="PII = Yes" className="p-1.5 rounded-md hover:bg-tier-red-light text-muted-foreground hover:text-tier-red-base transition-colors"><XCircle className="h-4 w-4" /></button>
                          </>
                        ) : (
                          <>
                            <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'Approved'}))} title="Approved" className="p-1.5 rounded-md hover:bg-tier-green-light text-muted-foreground hover:text-tier-green-base transition-colors"><CheckCircle2 className="h-4 w-4" /></button>
                            <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'Restricted'}))} title="Restricted" className="p-1.5 rounded-md hover:bg-tier-amber-light text-muted-foreground hover:text-tier-amber-base transition-colors"><AlertTriangle className="h-4 w-4" /></button>
                            <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'Prohibited'}))} title="Prohibited" className="p-1.5 rounded-md hover:bg-tier-red-light text-muted-foreground hover:text-tier-red-base transition-colors"><XCircle className="h-4 w-4" /></button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </AttestGroup>
          )}

          {dismissible.length > 0 && (
            <AttestGroup title={`Dismissible findings (${dismissible.length})`}
              onDismissAll={() => { const next = {...decisions}; dismissible.forEach((c) => { next[`dismiss-${c.rule_id}-${c.table_name}`] = 'Dismissed'; }); setDecisions(next); }}
            >
              {dismissible.map((c) => {
                const key = `dismiss-${c.rule_id}-${c.table_name}`;
                const decided = decisions[key];
                return (
                  <div key={key} className="flex items-center justify-between gap-3 border border-border rounded-lg px-4 py-2.5">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-muted text-muted-foreground shrink-0">dismiss?</span>
                      <span className="text-[13px] truncate"><b>{c.title}</b> on <code className="bg-muted px-1 rounded text-[11px]">{c.table_name}</code></span>
                    </div>
                    {decided ? (
                      <span className="text-[11px] text-muted-foreground font-semibold shrink-0">Dismissed</span>
                    ) : (
                      <button type="button" onClick={() => setDecisions((p) => ({...p, [key]: 'Dismissed'}))} title="Dismiss" className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"><MinusCircle className="h-4 w-4" /></button>
                    )}
                  </div>
                );
              })}
            </AttestGroup>
          )}
        </div>
      )}

      {hasDecisions && open && (
        <div className="mt-4 pl-6 flex items-center gap-3">
          <Button size="sm" disabled={!hasActionable || rescoring} onClick={handleApplyDecisions}>
            {rescoring && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {rescoring ? 'Rescoring...' : 'Apply Decisions & Rescore'}
          </Button>
          {!hasActionable && hasDecisions && (
            <span className="text-[11px] text-muted-foreground">Confirmed issues keep scores unchanged — approve or acknowledge to rescore.</span>
          )}
          {rescoreError && <span className="text-[11px] text-tier-red-base">{rescoreError}</span>}
        </div>
      )}
    </CardContent></Card>
  );
}

function AttestGroup({ title, children, onApproveAll, onDismissAll, onRestrictAll }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 w-full px-4 py-3">
        <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-2 flex-1 text-left hover:bg-muted/15 transition-colors">
          <ChevronDown className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform duration-200', !open && '-rotate-90')} />
          <span className="text-[13px] font-semibold">{title}</span>
        </button>
        <div className="flex gap-1 shrink-0">
          {onDismissAll && <button type="button" onClick={onDismissAll} className="text-[10px] font-medium px-2 py-1 rounded border border-border text-muted-foreground hover:bg-muted transition-colors">Dismiss all</button>}
          {onApproveAll && <button type="button" onClick={onApproveAll} className="text-[10px] font-medium px-2 py-1 rounded border border-tier-green-base/30 text-tier-green-base hover:bg-tier-green-light transition-colors">Approve all</button>}
          {onRestrictAll && <button type="button" onClick={onRestrictAll} className="text-[10px] font-medium px-2 py-1 rounded border border-tier-red-base/30 text-tier-red-base hover:bg-tier-red-light transition-colors">Restrict all</button>}
        </div>
      </div>
      {open && <div className="space-y-2 px-3 pb-3">{children}</div>}
    </div>
  );
}

// ─── Shared helpers ──────────────────────────────────────────────────────────
function CollapsibleSection({ title, subtitle, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="surface-vignette-subtle"><CardContent className="p-6">
      <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-2 w-full text-left mb-1">
        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform duration-200', !open && '-rotate-90')} />
        <h2 className="font-display text-lg font-bold">{title}</h2>
        {subtitle && <span className="text-[11px] text-muted-foreground ml-2">{subtitle}</span>}
      </button>
      {open && <div className="mt-3">{children}</div>}
    </CardContent></Card>
  );
}

function DownloadMdButton({ data }) {
  const [error, setError] = useState(null);
  const download = async () => {
    setError(null);
    try {
      const md = await api.exportMarkdown(data);
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'ai_readiness_report.md'; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err.message || 'Download failed'); }
  };
  return (
    <div className="inline-flex items-center gap-2">
      <Button variant="default" size="sm" onClick={download}><FileText className="h-3.5 w-3.5" /> Download report</Button>
      {error && <span className="text-[11px] text-tier-red-base">{error}</span>}
    </div>
  );
}

// ─── Purpose Dropdown (persistent on Dashboard) ─────────────────────────────
function PurposeDropdown({ selectedPurpose, onPurposeChange, loading }) {
  const [open, setOpen] = useState(false);
  const allArchetypes = ARCHETYPE_FAMILIES.flatMap(f => (f.archetypes || []).map(a => ({ ...a, family: f.label })));
  const selected = allArchetypes.find(a => a.id === selectedPurpose);

  return (
    <div className="relative">
      <div className="flex items-center gap-3">
        <span className="font-nav text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Purpose</span>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg border text-[13px] font-medium transition-colors min-w-[200px]',
            selectedPurpose ? 'border-primary bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:border-primary/50'
          )}
        >
          <span className="flex-1 text-left truncate">
            {selected ? selected.label : 'Baseline data quality (no purpose)'}
          </span>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" /> :
            <ChevronDown className={cn('h-3.5 w-3.5 shrink-0 transition-transform', open && 'rotate-180')} />}
        </button>
        {selectedPurpose && (
          <button
            type="button"
            onClick={() => onPurposeChange('')}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            clear
          </button>
        )}
      </div>
      {open && (
        <div className="absolute z-40 top-full mt-1.5 left-0 w-[320px] bg-background border border-border rounded-xl shadow-lg p-3 max-h-[380px] overflow-y-auto">
          {/* Baseline option */}
          <button
            type="button"
            onClick={() => { onPurposeChange(''); setOpen(false); }}
            className={cn(
              'w-full text-left px-3 py-2 rounded-lg text-[12px] transition-colors mb-1',
              !selectedPurpose ? 'bg-primary/10 font-semibold' : 'hover:bg-muted/30'
            )}
          >
            Baseline data quality
          </button>
          {/* Grouped archetypes */}
          {ARCHETYPE_FAMILIES.map((fam) => (
            <div key={fam.id} className="mt-2">
              <p className="font-nav text-[9px] uppercase tracking-wide text-muted-foreground/60 px-3 mb-1">{fam.label}</p>
              {(fam.archetypes || []).map((arch) => (
                <button
                  key={arch.id}
                  type="button"
                  onClick={() => { onPurposeChange(arch.id); setOpen(false); }}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-lg text-[12px] transition-colors',
                    selectedPurpose === arch.id ? 'bg-primary/10 font-semibold' : 'hover:bg-muted/30'
                  )}
                >
                  {arch.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Runbook modal ───────────────────────────────────────────────────────────
const CRIT_COLORS = { Critical: 'text-tier-red-base', High: 'text-orange-500', Medium: 'text-muted-foreground', Low: 'text-muted-foreground/60' };

function RunbookModal({ result, onClose }) {
  const download = () => {
    if (!result?.markdown) return;
    const blob = new Blob([result.markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'ai_readiness_runbook.md'; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-8 overflow-auto" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-background rounded-2xl max-w-[880px] w-full p-7 shadow-2xl">
        <div className="flex justify-between items-center mb-1">
          <div className="flex items-center gap-3">
            <h2 className="font-display text-xl font-bold text-primary">Remediation runbook</h2>
            <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded bg-violet-600 text-white">AI · advisory</span>
          </div>
          <button type="button" onClick={onClose} className="text-muted-foreground text-xl leading-none hover:text-foreground">&#x2715;</button>
        </div>
        <p className="text-[13px] text-muted-foreground mb-4">Technical instructions for data engineers. Advisory — does not affect the score.</p>
        {result?.structured?.tables?.map((t) => (
          <div key={t.table_name} className="border border-border rounded-xl p-4 mb-3">
            <h3 className="font-display text-[16px] font-bold">{t.table_name}</h3>
            <div className="space-y-3 mt-3">
              {t.steps.map((step, i) => (
                <div key={i} className="mb-3">
                  <div className="flex items-center gap-2">
                    {step.criticality && <span className={cn('text-[11px] font-semibold uppercase tracking-wide', CRIT_COLORS[step.criticality] || 'text-muted-foreground')}>{step.criticality}</span>}
                    <p className="font-semibold text-[12.5px]">{i + 1}. {step.issue}</p>
                  </div>
                  {step.columns?.length > 0 && (
                    <p className="text-[11px] text-muted-foreground mt-0.5 pl-3 font-mono">{step.columns.join(', ')}</p>
                  )}
                  {step.evidence_summary && (
                    <p className="text-[11px] text-muted-foreground mt-0.5 pl-3">{step.evidence_summary}</p>
                  )}
                  <p className="text-[12.5px] text-foreground/80 pl-3 border-l-2 border-border mt-1">{step.recommendation}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
        {result?.markdown && !result?.structured && (
          <pre className="text-[12px] font-mono bg-muted/30 rounded-xl p-5 overflow-auto max-h-[60vh] whitespace-pre-wrap">{result.markdown}</pre>
        )}
        <div className="flex gap-3 mt-5">
          <Button variant="default" size="sm" onClick={download} disabled={!result?.markdown}><FileText className="h-3.5 w-3.5" /> Download .md</Button>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}
