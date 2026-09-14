import { useState, useEffect } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { getMeCache } from '@/lib/user';
import { api } from '@/lib/api';
import { Wifi, WifiOff, RefreshCw, Users, BarChart3, Settings } from 'lucide-react';

export default function Console() {
  const me = getMeCache();
  if (!me?.is_superuser) {
    return (
      <section className="container py-24 text-center">
        <p className="text-muted-foreground">
          Access denied. Superuser privileges required.
        </p>
      </section>
    );
  }

  return (
    <section className="container py-12 animate-card-rise">
      <div className="max-w-6xl mx-auto">
        <h1 className="font-display text-3xl font-light mb-2">Developer Console</h1>
        <p className="font-nav text-[13px] text-muted-foreground mb-8">
          Superuser diagnostics - {me.email}
        </p>

        <Tabs defaultValue="llm" className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="llm">LLM Connection</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="runs">Assessments</TabsTrigger>
            <TabsTrigger value="system">System</TabsTrigger>
          </TabsList>

          {/* forceMount keeps panels mounted so useEffect doesn't re-fire on every tab switch */}
          <TabsContent value="llm" forceMount className="data-[state=inactive]:hidden"><LlmPanel /></TabsContent>
          <TabsContent value="users" forceMount className="data-[state=inactive]:hidden"><UsersPanel /></TabsContent>
          <TabsContent value="runs" forceMount className="data-[state=inactive]:hidden"><RunsPanel /></TabsContent>
          <TabsContent value="system" forceMount className="data-[state=inactive]:hidden"><SystemPanel /></TabsContent>
        </Tabs>
      </div>
    </section>
  );
}

// ─── LLM Connection ──────────────────────────────────────────────────────

function LlmPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const test = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await api.adminLlmStatus());
    } catch (e) {
      setError(e.message);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { test(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="font-display text-xl font-normal">Cortex LLM Status</CardTitle>
        <Button variant="outline" size="sm" onClick={test} disabled={loading}>
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          {loading ? 'Testing...' : 'Test Connection'}
        </Button>
      </CardHeader>
      <CardContent>
        {error && <p className="font-mono text-sm text-tier-red-base">{error}</p>}
        {status && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {status.ok
                ? <Wifi className="h-5 w-5 text-tier-green-base" />
                : <WifiOff className="h-5 w-5 text-tier-red-base" />}
              <Badge variant={status.ok ? 'green' : 'red'}>
                {status.ok ? 'Connected' : 'Disconnected'}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground font-nav text-[12px]">Latency</p>
                <p className="font-mono">{status.latency_ms ?? '-'} ms</p>
              </div>
              <div>
                <p className="text-muted-foreground font-nav text-[12px]">Model Config</p>
                <p className="font-mono">{status.model_config ?? '-'}</p>
              </div>
              {status.error && (
                <div className="col-span-2">
                  <p className="text-muted-foreground font-nav text-[12px]">Error</p>
                  <p className="font-mono text-tier-red-base">{status.error}</p>
                </div>
              )}
              <div>
                <p className="text-muted-foreground font-nav text-[12px]">Token Cached</p>
                <p className="font-mono">{status.token_cached ? 'Yes' : 'No'}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Users ───────────────────────────────────────────────────────────────

function UsersPanel() {
  const [data, setData] = useState({ users: [], total: 0 });
  const [page, setPage] = useState(0);
  const [error, setError] = useState(null);

  const load = async (p = 0) => {
    setError(null);
    try {
      setData(await api.adminGetUsers(10, p * 10));
      setPage(p);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (userId, current) => {
    try {
      await api.adminUpdateUser(userId, { is_superuser: !current });
      load(page);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl font-normal flex items-center gap-2">
          <Users className="h-5 w-5" />
          All Users ({data.total})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="font-mono text-sm text-tier-red-base mb-4">{error}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left font-nav text-[12px] text-muted-foreground">
                <th className="pb-2 pr-4">Email</th>
                <th className="pb-2 pr-4">Role</th>
                <th className="pb-2 pr-4">Superuser</th>
                <th className="pb-2 pr-4">Runs</th>
                <th className="pb-2 pr-4">Last seen</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.user_id} className="border-b border-border/40">
                  <td className="py-3 pr-4 font-mono text-[13px]">{u.email || u.user_id}</td>
                  <td className="py-3 pr-4">{u.role || '-'}</td>
                  <td className="py-3 pr-4">
                    {u.is_superuser
                      ? <Badge variant="green">Yes</Badge>
                      : <span className="text-muted-foreground">No</span>}
                  </td>
                  <td className="py-3 pr-4 font-mono">{u.run_count}</td>
                  <td className="py-3 pr-4 text-muted-foreground text-[12px]">
                    {u.last_seen ? new Date(u.last_seen).toLocaleDateString() : '-'}
                  </td>
                  <td className="py-3">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggle(u.user_id, u.is_superuser)}
                    >
                      {u.is_superuser ? 'Revoke' : 'Grant'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.total > 10 && (
          <div className="flex items-center gap-2 mt-4">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => load(page - 1)}>
              Prev
            </Button>
            <span className="font-nav text-[12px] text-muted-foreground">
              Page {page + 1} of {Math.ceil(data.total / 10)}
            </span>
            <Button variant="outline" size="sm" disabled={(page + 1) * 10 >= data.total} onClick={() => load(page + 1)}>
              Next
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Assessments ─────────────────────────────────────────────────────────

function RunsPanel() {
  const [data, setData] = useState({ runs: [], total: 0 });
  const [page, setPage] = useState(0);
  const [error, setError] = useState(null);

  const load = async (p = 0) => {
    setError(null);
    try {
      setData(await api.adminGetRuns(10, p * 10));
      setPage(p);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl font-normal flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          All Assessments ({data.total})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="font-mono text-sm text-tier-red-base mb-4">{error}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left font-nav text-[12px] text-muted-foreground">
                <th className="pb-2 pr-4">User</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4">Score</th>
                <th className="pb-2 pr-4">Tier</th>
                <th className="pb-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr
                  key={r.run_id}
                  className="border-b border-border/40 hover:bg-muted/30 cursor-pointer"
                  onClick={() => window.open(`/assess/${r.run_id}`, '_blank')}
                >
                  <td className="py-3 pr-4 font-mono text-[13px]">{r.email || r.user_id}</td>
                  <td className="py-3 pr-4">{r.source_type}: {r.source_name}</td>
                  <td className="py-3 pr-4 font-mono font-semibold">{r.overall_score}</td>
                  <td className="py-3 pr-4">
                    <Badge variant={r.tier}>{r.tier}</Badge>
                  </td>
                  <td className="py-3 text-muted-foreground text-[12px]">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.total > 10 && (
          <div className="flex items-center gap-2 mt-4">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => load(page - 1)}>
              Prev
            </Button>
            <span className="font-nav text-[12px] text-muted-foreground">
              Page {page + 1} of {Math.ceil(data.total / 10)}
            </span>
            <Button variant="outline" size="sm" disabled={(page + 1) * 10 >= data.total} onClick={() => load(page + 1)}>
              Next
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── System Diagnostics ──────────────────────────────────────────────────

function SystemPanel() {
  const [sys, setSys] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.adminSystem()
      .then(setSys)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="font-mono text-sm text-tier-red-base">{error}</p>;
  if (!sys) return <p className="text-muted-foreground">Loading...</p>;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-lg font-normal flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Infrastructure
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="Database" value={sys.db_connected ? 'Connected' : 'Disconnected'}
            ok={sys.db_connected} />
          <Row label="DB Pool Size" value={sys.db_pool_size} />
          <Row label="Active Jobs" value={sys.active_jobs} />
          <Row label="Jobs In Memory" value={sys.total_jobs_in_memory} />
          <Row label="Uptime" value={`${Math.floor(sys.uptime_s / 60)} min`} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-lg font-normal">Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {Object.entries(sys.config || {}).map(([k, v]) => (
            <Row
              key={k}
              label={k.replace(/_/g, ' ')}
              value={typeof v === 'object' ? JSON.stringify(v) : String(v)}
            />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value, ok }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-nav text-[12px] text-muted-foreground">{label}</span>
      <span className={cn('font-mono text-[13px]', ok === false && 'text-tier-red-base', ok === true && 'text-tier-green-base')}>
        {value}
      </span>
    </div>
  );
}
