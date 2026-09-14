import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Layout from '@/Layout.jsx';
import Dashboard from '@/pages/Dashboard.jsx';
import { api } from '@/lib/api';
import { DIMENSIONS } from '@/lib/dimensions';

function scoreToTier(score) {
  if (score >= 65) return 'green';
  if (score >= 40) return 'yellow';
  return 'red';
}

function buildDims(dimensionScores) {
  return DIMENSIONS.map((dim) => {
    const score = dimensionScores?.[dim.id] ?? 0;
    return { id: dim.id, label: dim.label, weight: dim.weight, score, tier: scoreToTier(score), checks: [] };
  });
}

// Fallback adapter for legacy rows (result_json = null). Produces a minimal
// SchemaAssessment shape from the denormalized columns - checks will be empty.
function adaptLegacyRun(run) {
  const tables = run.tables.map((t) => ({
    table_name: t.table_name,
    row_count: 0,
    column_count: 0,
    overall_score: t.table_score,
    tier: t.tier,
    dimensions: buildDims(t.dimension_scores),
    summary: '',
    recommendations: t.recommendations ?? [],
  }));

  const schemaDims = DIMENSIONS.map((dim) => {
    const scores = run.tables.map((t) => t.dimension_scores?.[dim.id] ?? 0);
    const score = scores.length > 0
      ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
      : 0;
    return { id: dim.id, label: dim.label, weight: dim.weight, score, tier: scoreToTier(score), checks: [] };
  });

  return {
    overall_score: run.overall_score,
    tier: run.tier,
    summary: '',
    top_priorities: [],
    table_count: run.table_count,
    dimensions: schemaDims,
    tables,
    metadata_profile: null,
  };
}

export default function AssessRunView() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState('loading'); // 'loading' | 'ready' | 'notfound' | 'error'
  const [result, setResult] = useState(null);
  const [isLegacy, setIsLegacy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getRun(runId).then((data) => {
      if (!cancelled) {
        if (data.result) {
          setResult(data.result);
          setIsLegacy(false);
        } else {
          setResult(adaptLegacyRun(data));
          setIsLegacy(true);
        }
        setState('ready');
      }
    }).catch((err) => {
      if (!cancelled) {
        if (err.status === 401) {
          navigate('/');
        } else if (err.status === 404) {
          setState('notfound');
        } else {
          setState('error');
        }
      }
    });
    return () => { cancelled = true; };
  }, [runId]);

  if (state === 'loading') {
    return (
      <Layout variant="white">
        <section className="container py-32 animate-card-rise">
          <div className="max-w-5xl mx-auto">
            <Card className="border-dashed">
              <CardContent className="py-12 text-center text-muted-foreground font-nav text-sm">
                Loading assessment...
              </CardContent>
            </Card>
          </div>
        </section>
      </Layout>
    );
  }

  if (state === 'notfound' || state === 'error') {
    return (
      <Layout variant="white">
        <section className="container py-32 text-center animate-card-rise">
          <p className="font-nav text-[14px] font-medium text-muted-foreground">
            {state === 'notfound' ? '404 · Not Found' : 'Error'}
          </p>
          <h1 className="font-display text-5xl font-light text-primary tracking-tight mt-4 mb-3">
            Assessment not found.
          </h1>
          <p className="text-muted-foreground max-w-md mx-auto mb-8">
            {state === 'notfound'
              ? 'This assessment doesn\'t exist or belongs to another user.'
              : 'Something went wrong loading this assessment.'}
          </p>
          <Button asChild>
            <Link to="/history">
              <ArrowLeft className="h-4 w-4" />
              Back to History
            </Link>
          </Button>
        </section>
      </Layout>
    );
  }

  return (
    <Layout variant="white">
      {isLegacy && (
        <div className="container pt-6">
          <div className="max-w-5xl mx-auto">
            <p className="font-nav text-[12px] text-muted-foreground border border-border rounded-lg px-4 py-2.5 bg-muted/30">
              Full detail not stored for this assessment - it was run before detail capture was enabled.
              Top-level scores are still available below.
            </p>
          </div>
        </div>
      )}
      <Dashboard result={result} onRestart={() => navigate('/history')} />
    </Layout>
  );
}
