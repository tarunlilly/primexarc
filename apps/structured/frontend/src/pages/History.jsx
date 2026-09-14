import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { AssessmentRow } from '@/pages/Account.jsx';

export default function History() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState(null);
  const [confirm, setConfirm] = useState(null); // run_id | '__all__' | null

  useEffect(() => {
    let cancelled = false;
    api.getHistory(50).then((data) => {
      if (!cancelled) setRuns(data);
    }).catch(() => {
      if (!cancelled) setRuns([]);
    });
    return () => { cancelled = true; };
  }, []);

  const loading = runs === null;
  const count = runs?.length ?? 0;

  function handleDeleteOne(runId) {
    setConfirm(runId);
  }

  async function confirmDelete() {
    if (!confirm) return;
    try {
      if (confirm === '__all__') {
        await api.clearHistory();
        setRuns([]);
      } else {
        await api.deleteRun(confirm);
        setRuns((prev) => prev.filter((r) => r.run_id !== confirm));
      }
    } catch {
      // silently ignore - row stays visible, user can retry
    } finally {
      setConfirm(null);
    }
  }

  const confirmRun = confirm && confirm !== '__all__'
    ? runs?.find((r) => r.run_id === confirm)
    : null;

  return (
    <section className="container py-12 md:py-16 animate-card-rise">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-end justify-between mb-10">
          <div>
            <p className="font-nav text-[13px] font-medium text-muted-foreground mb-1">
              Assessment History
            </p>
            <h1 className="font-display text-5xl md:text-6xl font-light tracking-tight text-primary leading-none">
              {loading ? '-' : `${count} assessment${count !== 1 ? 's' : ''}`}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {!loading && count > 0 && (
              <Button
                variant="ghost"
                onClick={() => setConfirm('__all__')}
                className="text-muted-foreground hover:text-tier-red-base"
              >
                <Trash2 className="h-4 w-4" />
                Clear all
              </Button>
            )}
            <Button asChild>
              <Link to="/assess">
                New Assessment
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>

        {/* Confirmation dialog */}
        {confirm && (
          <Card className="mb-6 border-tier-red-base/30 bg-tier-red-light/20">
            <CardContent className="py-4 flex items-center justify-between gap-4">
              <p className="font-nav text-[13px] text-foreground">
                {confirm === '__all__'
                  ? `Delete all ${count} assessments? This cannot be undone.`
                  : `Delete "${confirmRun?.source_name ?? 'this assessment'}"? This cannot be undone.`}
              </p>
              <div className="flex items-center gap-2 shrink-0">
                <Button variant="ghost" size="sm" onClick={() => setConfirm(null)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  className="bg-tier-red-base hover:bg-tier-red-base/90 text-white"
                  onClick={confirmDelete}
                >
                  Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {loading ? (
          <Card className="border-dashed">
            <CardContent className="py-8 text-center text-muted-foreground font-nav text-sm">
              Loading history...
            </CardContent>
          </Card>
        ) : count === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-12 text-center text-muted-foreground">
              No assessments yet.{' '}
              <Link to="/assess" className="text-primary underline underline-offset-4">
                Start your first one.
              </Link>
            </CardContent>
          </Card>
        ) : (
          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {runs.map((run) => (
                <AssessmentRow
                  key={run.run_id}
                  run={run}
                  onDelete={handleDeleteOne}
                />
              ))}
            </ul>
          </Card>
        )}
      </div>
    </section>
  );
}
