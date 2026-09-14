import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, FileText, Database, Calendar, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getCurrentUser } from '@/lib/user';
import { TIER_LABELS, TIER_STYLES } from '@/lib/dimensions';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function Account() {
  const user = getCurrentUser();
  const [runs, setRuns] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.getHistory(3).then((data) => {
      if (!cancelled) setRuns(data);
    }).catch(() => {
      if (!cancelled) setRuns([]);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="container py-12 md:py-16 animate-card-rise">
      <div className="max-w-5xl mx-auto">
        <ProfileHeader user={user} />
        <RoleAndProducts user={user} />
        <AssessmentHistory runs={runs} />
      </div>
    </section>
  );
}

// ─── Profile header: avatar + name + email ─────────────────────────────────
function ProfileHeader({ user }) {
  return (
    <div className="flex items-center gap-5 mb-12">
      <span className="inline-flex items-center justify-center h-20 w-20 rounded-full bg-primary text-primary-foreground font-nav text-2xl font-semibold shrink-0">
        {user.initials}
      </span>
      <div className="min-w-0">
        <p className="font-nav text-[13px] font-medium text-muted-foreground mb-1">
          Account
        </p>
        <h1 className="font-display text-5xl md:text-6xl font-light tracking-tight text-primary leading-none">
          {user.name}
        </h1>
        <p className="text-muted-foreground mt-2">{user.email}</p>
      </div>
    </div>
  );
}

// ─── Role + data product ownership ─────────────────────────────────────────
function RoleAndProducts({ user }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
      <Card>
        <CardHeader className="pb-3">
          <CardDescription className="font-nav text-[12px] font-medium text-muted-foreground uppercase tracking-wider">
            Role
          </CardDescription>
          <CardTitle className="font-display text-2xl font-normal text-primary mt-1">
            {user.role ?? '-'}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardDescription className="font-nav text-[12px] font-medium text-muted-foreground uppercase tracking-wider">
            Team
          </CardDescription>
          <CardTitle className="font-display text-2xl font-normal text-primary mt-1">
            {user.team ?? '-'}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardDescription className="font-nav text-[12px] font-medium text-muted-foreground uppercase tracking-wider">
            Data Products Owned
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <ul className="space-y-1.5">
            {user.data_products.map((p) => (
              <li key={p} className="text-sm text-foreground leading-snug">
                · {p}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Recent assessments ────────────────────────────────────────────────────
function AssessmentHistory({ runs }) {
  const count = runs?.length ?? 0;
  const loading = runs === null;

  return (
    <section>
      <div className="flex items-end justify-between mb-5">
        <div>
          <p className="font-nav text-[14px] font-medium text-primary mb-1">
            Recent Assessments
          </p>
          <h2 className="font-display text-3xl font-light text-foreground tracking-tight">
            {loading ? '-' : `${count} recent assessment${count !== 1 ? 's' : ''}`}
          </h2>
        </div>
        <div className="flex items-center gap-3">
          {!loading && count > 0 && (
            <Button variant="ghost" asChild>
              <Link to="/history">
                See all
                <ArrowRight className="h-4 w-4" />
              </Link>
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

      {loading ? (
        <Card className="border-dashed">
          <CardContent className="py-8 text-center text-muted-foreground font-nav text-sm">
            Loading history...
          </CardContent>
        </Card>
      ) : count === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-muted-foreground">
            No assessments yet. Start your first one to see it here.
          </CardContent>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-border">
            {runs.map((run) => (
              <AssessmentRow key={run.run_id} run={run} />
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

export function AssessmentRow({ run, onDelete }) {
  const navigate = useNavigate();
  const styles = TIER_STYLES[run.tier];
  const Icon = run.source_type === 'db' ? Database : FileText;
  const date = new Date(run.created_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });

  return (
    <li
      className="flex items-center gap-5 px-5 py-4 hover:bg-muted/40 transition-colors cursor-pointer"
      onClick={() => navigate(`/assess/${run.run_id}`)}
    >
      <span className={cn('w-1 h-10 rounded-sm shrink-0', styles.bar)} aria-hidden />
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
        <div className="min-w-0">
          <p className="font-semibold text-foreground truncate">
            {run.source_name}
          </p>
          <div className="flex items-center gap-3 font-nav text-[12px] text-muted-foreground mt-0.5">
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {date}
            </span>
            <span>·</span>
            <span>
              {run.table_count} {run.source_type === 'db' ? 'table' : 'file'}
              {run.table_count !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </div>
      <Badge variant={run.tier} className="shrink-0">
        {TIER_LABELS[run.tier]}
      </Badge>
      <span className={cn('font-display text-2xl font-light leading-none w-12 text-right', styles.text)}>
        {run.overall_score}
      </span>
      {onDelete && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(run.run_id); }}
          className="ml-1 p-1.5 rounded-md text-muted-foreground hover:text-tier-red-base hover:bg-tier-red-light/40 transition-colors shrink-0"
          aria-label="Delete assessment"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      )}
    </li>
  );
}
