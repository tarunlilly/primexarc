import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight, ArrowLeft, Upload, Database, Loader2,
  X, AlertCircle, FileText,
} from 'lucide-react';
import Layout from '@/Layout.jsx';
import Dashboard from '@/pages/Dashboard.jsx';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { api, pollJob, ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';

// Wizard steps - STEPS.TABLES is DB-only; CSV mode skips it.
const STEPS = {
  ONBOARDING: 0,
  INPUT:      1,
  TABLES:     2,  // DB only
  LOADING:    3,
  DASHBOARD:  4,
};

const EMPTY_CREDS = {
  engine: 'postgres', host: '', port: 5432,
  database: '', username: '', password: '', ssl: true,
};

const LAST_RESULT_KEY = 'arc_last_result';
const ACTIVE_JOB_KEY = 'arc_active_assessment';
const STARTING_JOB_STALE_MS = 45_000;
const CANCELLING_STALE_MS = 30_000;
const CANCELLING_POLL_MS = 1_500;


function readActiveJob() {
  try {
    const serialized = localStorage.getItem(ACTIVE_JOB_KEY);
    if (!serialized) return null;
    const parsed = JSON.parse(serialized);
    if (
      parsed?.status === 'starting'
      && parsed?.createdAt
      && Date.now() - parsed.createdAt > STARTING_JOB_STALE_MS
    ) {
      localStorage.removeItem(ACTIVE_JOB_KEY);
      return null;
    }
    if (
      parsed?.status === 'cancelling'
      && parsed?.createdAt
      && Date.now() - parsed.createdAt > CANCELLING_STALE_MS
    ) {
      localStorage.removeItem(ACTIVE_JOB_KEY);
      return null;
    }
    return parsed?.mode && parsed?.status ? parsed : null;
  } catch {
    return null;
  }
}


function persistActiveJob(job) {
  if (!job) {
    localStorage.removeItem(ACTIVE_JOB_KEY);
    return;
  }

  try {
    localStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(job));
  } catch (error) {
    console.warn('Could not cache active assessment job in local storage.', error);
  }
}


function pluralize(count, noun) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}


function buildActiveJobSummary(mode, files, schemaName, selectedTables) {
  if (mode === 'db') {
    return `${pluralize(selectedTables.size, 'table')} in schema ${schemaName}`;
  }
  return `${pluralize(files.length, 'CSV file')}`;
}


function formatJobPhase(phase) {
  if (!phase) return '';
  return phase.replaceAll('_', ' ');
}

function persistLastResult(result) {
  const serialized = JSON.stringify(result);

  try {
    sessionStorage.setItem(LAST_RESULT_KEY, serialized);
    return true;
  } catch (error) {
    try {
      sessionStorage.removeItem(LAST_RESULT_KEY);
      sessionStorage.setItem(LAST_RESULT_KEY, serialized);
      return true;
    } catch (retryError) {
      console.warn('Could not cache latest assessment result in session storage.', retryError);
      return false;
    }
  }
}

export default function Assess() {
  const [step, setStep] = useState(STEPS.INPUT);
  const [mode, setMode] = useState('csv'); // 'csv' | 'db'
  const [loadingJob, setLoadingJob] = useState(null);
  const [cancellingJobId, setCancellingJobId] = useState(null);

  // CSV mode state
  const [files, setFiles] = useState([]);

  // DB mode state
  const [credentials, setCredentials] = useState(EMPTY_CREDS);
  const [schemaName, setSchemaName] = useState('public');
  const [tables, setTables] = useState([]);          // [{name, column_count, ...}]
  const [selectedTables, setSelectedTables] = useState(new Set());

  // Purpose picker state
  const [selectedPurpose, setSelectedPurpose] = useState('');
  const [semanticScan, setSemanticScan] = useState(true);

  // Shared state
  const [metadataFile, setMetadataFile] = useState(null);
  const [result, setResult] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(LAST_RESULT_KEY)); }
    catch { return null; }
  });
  const [activeJob, setActiveJobState] = useState(() => readActiveJob());
  const [error, setError] = useState(null);
  const activeJobRef = useRef(activeJob);
  const loadingJobRef = useRef(loadingJob);
  const stepRef = useRef(step);

  useEffect(() => {
    const syncActiveJob = (event) => {
      if (event.key === ACTIVE_JOB_KEY) {
        setActiveJobState(readActiveJob());
      }
    };

    window.addEventListener('storage', syncActiveJob);
    return () => window.removeEventListener('storage', syncActiveJob);
  }, []);

  useEffect(() => {
    activeJobRef.current = activeJob;
    if (!activeJob) {
      setCancellingJobId(null);
    }
  }, [activeJob]);

  useEffect(() => {
    loadingJobRef.current = loadingJob;
  }, [loadingJob]);

  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  useEffect(() => {
    if (!activeJob || activeJob.jobId || activeJob.status !== 'starting') return;

    const ageMs = Date.now() - (activeJob.createdAt || Date.now());
    if (ageMs >= STARTING_JOB_STALE_MS) {
      setActiveJob(null);
      return;
    }

    const timerId = window.setTimeout(() => {
      setActiveJob(null);
    }, STARTING_JOB_STALE_MS - ageMs);

    return () => window.clearTimeout(timerId);
  }, [activeJob]);

  // Variant for surface flip
  const variant =
    step === STEPS.DASHBOARD ? 'white' :
    step === STEPS.LOADING   ? 'crimson' : 'red';

  // Step navigation helpers
  const setActiveJob = (job) => {
    setActiveJobState(job);
    persistActiveJob(job);
  };

  const clearTrackedJob = () => {
    setLoadingJob(null);
    setActiveJob(null);
    setCancellingJobId(null);
  };

  const showCancelledState = (detail, nextStep) => {
    clearTrackedJob();
    setError({
      code: 'JOB_CANCELLED',
      detail: detail || 'Assessment cancelled. You can start a new assessment now.',
    });
    setStep(nextStep);
  };

  const showFailedState = (err, nextStep) => {
    clearTrackedJob();
    setError(err);
    setStep(nextStep);
  };

  const showCompletedState = (assessment) => {
    persistLastResult(assessment);
    clearTrackedJob();
    setResult(assessment);
    setError(null);
    setStep(STEPS.DASHBOARD);
  };

  useEffect(() => {
    if (!activeJob?.jobId || activeJob.status !== 'cancelling') return;

    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      while (!cancelled) {
        try {
          const snapshot = await api.getJob(activeJob.jobId, controller.signal);
          if (cancelled || activeJobRef.current?.jobId !== activeJob.jobId) return;

          if (snapshot.status === 'cancelling') {
            setActiveJob({
              ...activeJobRef.current,
              status: snapshot.status,
              progress: snapshot.progress ?? activeJobRef.current?.progress ?? 0,
              phase: snapshot.phase || activeJobRef.current?.phase || 'cancelling',
            });
          } else if (snapshot.status === 'cancelled') {
            showCancelledState(
              snapshot.error?.detail,
              stepRef.current === STEPS.ONBOARDING ? STEPS.INPUT : stepRef.current,
            );
            return;
          } else if (snapshot.status === 'done' && snapshot.result) {
            showCompletedState(snapshot.result);
            return;
          } else if (snapshot.status === 'failed') {
            showFailedState(
              {
                code: snapshot.error?.code || 'JOB_FAILED',
                detail: snapshot.error?.detail || 'Assessment failed.',
              },
              stepRef.current === STEPS.ONBOARDING ? STEPS.INPUT : stepRef.current,
            );
            return;
          }
        } catch (err) {
          if (cancelled || err.name === 'AbortError') return;
          const ae = err instanceof ApiError ? err : null;
          if (ae?.code === 'JOB_NOT_FOUND') {
            showCancelledState(
              'Assessment is no longer active. You can start a new assessment now.',
              stepRef.current === STEPS.ONBOARDING ? STEPS.INPUT : stepRef.current,
            );
            return;
          }
          if (ae?.code === 'TOKEN_EXPIRED' || ae?.status === 401) {
            showCancelledState(
              'Session expired during cancellation. The assessment has been cleared.',
              stepRef.current === STEPS.ONBOARDING ? STEPS.INPUT : stepRef.current,
            );
            return;
          }
        }

        await new Promise((resolve) => window.setTimeout(resolve, CANCELLING_POLL_MS));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeJob?.jobId, activeJob?.status]);

  const resumeActiveJob = () => {
    if (!activeJob?.jobId) return;
    setError(null);
    setLoadingJob(activeJob);
    setStep(STEPS.LOADING);
  };

  const cancelActiveJob = async ({ nextStep } = {}) => {
    const jobId = activeJobRef.current?.jobId;
    if (!jobId || cancellingJobId === jobId) return;

    setError(null);
    setCancellingJobId(jobId);

    try {
      const snapshot = await api.cancelJob(jobId);
      const sameJobStillTracked = activeJobRef.current?.jobId === jobId
        || loadingJobRef.current?.jobId === jobId;

      if (!sameJobStillTracked && stepRef.current === STEPS.DASHBOARD) {
        setCancellingJobId(null);
        return;
      }

      if (snapshot.status === 'done' && snapshot.result) {
        showCompletedState(snapshot.result);
        return;
      }

      if (snapshot.status === 'failed') {
        showFailedState(
          {
            code: snapshot.error?.code || 'JOB_FAILED',
            detail: snapshot.error?.detail || 'Assessment failed.',
          },
          nextStep ?? STEPS.INPUT,
        );
        return;
      }

      if (snapshot.status === 'cancelling') {
        setActiveJob({
          ...activeJobRef.current,
          status: snapshot.status,
          progress: snapshot.progress ?? activeJobRef.current?.progress ?? 0,
          phase: snapshot.phase || 'cancelling',
        });
        setLoadingJob(null);
        setStep(nextStep ?? stepRef.current);
        return;
      }

      showCancelledState(snapshot.error?.detail, nextStep ?? stepRef.current);
    } catch (err) {
      const ae = err instanceof ApiError ? err : null;
      if (ae?.code === 'JOB_NOT_FOUND') {
        showCancelledState('Assessment is no longer active. You can start a new assessment now.', nextStep ?? STEPS.INPUT);
        return;
      }

      setCancellingJobId(null);
      setError({
        code: ae?.code || 'UNKNOWN',
        detail: ae?.message || String(err),
      });
    }
  };

  const goBack = () => {
    setError(null);
    if (step === STEPS.TABLES) return setStep(STEPS.INPUT);
    if (step === STEPS.INPUT) return; // Already at first step
    if (step === STEPS.LOADING) return setStep(mode === 'db' ? STEPS.TABLES : STEPS.INPUT);
  };

  const reset = () => {
    setStep(STEPS.INPUT);
    setMode('csv');
    setFiles([]);
    setCredentials(EMPTY_CREDS);
    setSchemaName('public');
    setTables([]);
    setSelectedTables(new Set());
    setSelectedPurpose('');
    setSemanticScan(true);
    setMetadataFile(null);
    setResult(null);
    clearTrackedJob();
    setError(null);
    sessionStorage.removeItem(LAST_RESULT_KEY);
  };

  const activeJobIsCancelling = activeJob?.status === 'cancelling'
    || cancellingJobId === activeJob?.jobId;

  return (
    <Layout variant={variant}>
      <div key={step} className="animate-card-rise flex-1 flex flex-col">
        {activeJob && step !== STEPS.LOADING && step !== STEPS.DASHBOARD && (
          <ActiveAssessmentBanner
            job={activeJob}
            isCancelling={activeJobIsCancelling}
            onResume={resumeActiveJob}
            onCancel={() => cancelActiveJob({ nextStep: step === STEPS.ONBOARDING ? STEPS.INPUT : step })}
          />
        )}

        {step === STEPS.ONBOARDING && (
          <Onboarding onStart={() => setStep(STEPS.INPUT)} />
        )}

        {step === STEPS.INPUT && (
          <DataInput
            mode={mode} setMode={setMode}
            files={files} setFiles={setFiles}
            credentials={credentials} setCredentials={setCredentials}
            schemaName={schemaName} setSchemaName={setSchemaName}
            metadataFile={metadataFile} setMetadataFile={setMetadataFile}
            selectedPurpose={selectedPurpose} setSelectedPurpose={setSelectedPurpose}
            semanticScan={semanticScan} setSemanticScan={setSemanticScan}
            activeJob={activeJob}
            isCancellingActiveJob={activeJobIsCancelling}
            error={error} setError={setError}
            onBack={goBack}
            onResumeActiveJob={resumeActiveJob}
            onCsvNext={() => {
              setLoadingJob(null);
              setStep(STEPS.LOADING);
            }}
            onDbTablesLoaded={(rows) => {
              setTables(rows);
              setSelectedTables(new Set(rows.map((t) => t.name)));
              setStep(STEPS.TABLES);
            }}
          />
        )}

        {step === STEPS.TABLES && (
          <TableSelection
            tables={tables}
            selected={selectedTables}
            setSelected={setSelectedTables}
            activeJob={activeJob}
            isCancellingActiveJob={activeJobIsCancelling}
            error={error}
            onDismissError={() => setError(null)}
            onBack={goBack}
            onResumeActiveJob={resumeActiveJob}
            onRun={() => {
              setLoadingJob(null);
              setStep(STEPS.LOADING);
            }}
          />
        )}

        {step === STEPS.LOADING && (
          <LoadingScreen
            mode={mode} files={files}
            credentials={credentials} schemaName={schemaName}
            selectedTables={selectedTables}
            metadataFile={metadataFile}
            selectedPurpose={selectedPurpose}
            semanticScan={semanticScan}
            existingJob={loadingJob}
            activeJob={activeJob}
            onRunInBackground={() => {
              setLoadingJob(null);
              goBack();
            }}
            onCancelJob={() => cancelActiveJob({ nextStep: mode === 'db' ? STEPS.TABLES : STEPS.INPUT })}
            onJobStarted={setActiveJob}
            onJobUpdated={setActiveJob}
            onJobCleared={clearTrackedJob}
            onComplete={showCompletedState}
            onError={(err) => {
              setCancellingJobId(null);
              if (err.code === 'JOB_CANCELLED') {
                showCancelledState(err.detail, mode === 'db' ? STEPS.TABLES : STEPS.INPUT);
                return;
              }
              setLoadingJob(null);
              if (!err.preserveActiveJob) {
                setActiveJob(null);
              }
              setError(err);
              setStep(STEPS.INPUT);
            }}
          />
        )}

        {step === STEPS.DASHBOARD && (
          <Dashboard result={result} onRestart={reset} onRescore={(rescored) => { setResult(rescored); persistLastResult(rescored); }} />
        )}
      </div>
    </Layout>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 0 · Onboarding
// ═══════════════════════════════════════════════════════════════════════════
function Onboarding({ onStart }) {
  return (
    <section className="container py-12 md:py-16">
      <div className="max-w-3xl mx-auto rounded-3xl bg-white/14 backdrop-blur-sm border border-white/25 px-8 md:px-12 py-20 md:py-24 text-center shadow-xl">
        {/* <p className="font-nav text-[14px] font-medium text-white/80 mb-6">
          Step 01 · Begin
        </p> */}
        <h1 className="font-display text-5xl md:text-7xl font-light leading-tight tracking-tight text-white max-w-3xl mx-auto">
          Let's evaluate{' '}
          <em className="italic font-extralight">your dataset.</em>
        </h1>
        <p className="mt-8 text-lg text-white/90 max-w-xl mx-auto leading-relaxed">
          You'll provide a CSV file or a database connection. We profile the data
          server-side: raw rows never leave the parser. The whole assessment
          takes about a minute.
        </p>
        <div className="mt-10 flex items-center justify-center">
          <Button variant="onRed" size="lg" onClick={onStart}>
            Begin
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 1 · Data Input - CSV upload OR DB credentials
// ═══════════════════════════════════════════════════════════════════════════
function DataInput({
  mode, setMode,
  files, setFiles,
  credentials, setCredentials,
  schemaName, setSchemaName,
  metadataFile, setMetadataFile,
  selectedPurpose, setSelectedPurpose,
  semanticScan, setSemanticScan,
  activeJob,
  isCancellingActiveJob,
  error, setError,
  onBack, onResumeActiveJob, onCsvNext, onDbTablesLoaded,
}) {
  return (
    <section className="container py-20">
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-10">
          {/* <p className="font-nav text-[14px] font-medium text-white/75 mb-4">
            Step 02 · Source
          </p> */}
          <h1 className="font-display text-5xl md:text-6xl font-light leading-tight tracking-tight text-white">
            Where's your data?
          </h1>
        </div>

        <Tabs value={mode} onValueChange={(v) => { setMode(v); setError(null); }}>
          <TabsList className="grid grid-cols-2 w-full max-w-md mx-auto bg-white/10 border border-white/15">
            <TabsTrigger value="csv" className="data-[state=active]:bg-white data-[state=active]:text-lilly-red text-white/80">
              <Upload className="h-4 w-4 mr-2" />
              CSV Files
            </TabsTrigger>
            <TabsTrigger value="db" className="data-[state=active]:bg-white data-[state=active]:text-lilly-red text-white/80">
              <Database className="h-4 w-4 mr-2" />
              Database
            </TabsTrigger>
          </TabsList>

          <TabsContent value="csv">
            <CsvPanel files={files} setFiles={setFiles}
                      metadataFile={metadataFile} setMetadataFile={setMetadataFile} />
          </TabsContent>

          <TabsContent value="db">
            <DbPanel
              credentials={credentials} setCredentials={setCredentials}
              schemaName={schemaName} setSchemaName={setSchemaName}
              metadataFile={metadataFile} setMetadataFile={setMetadataFile}
            />
          </TabsContent>
        </Tabs>

        <PurposePicker
          selectedPurpose={selectedPurpose}
          setSelectedPurpose={setSelectedPurpose}
          semanticScan={semanticScan}
          setSemanticScan={setSemanticScan}
        />

        {error && <ErrorBanner error={error} onDismiss={() => setError(null)} />}

        <div className="mt-10 flex items-center justify-center gap-3">
          <Button variant="ghostOnRed" size="lg" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          {activeJob ? (
            <Button variant="onRed" size="lg" onClick={onResumeActiveJob} disabled={!activeJob.jobId || isCancellingActiveJob}>
              {isCancellingActiveJob
                ? 'Cancelling Assessment'
                : activeJob.jobId
                  ? 'Resume Running Assessment'
                  : 'Preparing Resume Link'}
              {!isCancellingActiveJob && activeJob.jobId && <ArrowRight className="h-4 w-4" />}
            </Button>
          ) : mode === 'csv' ? (
            <Button
              variant="onRed" size="lg"
              disabled={files.length === 0}
              onClick={onCsvNext}
            >
              Run Assessment
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : (
            <DbConnectButton
              credentials={credentials}
              schemaName={schemaName}
              onError={setError}
              onTablesLoaded={onDbTablesLoaded}
            />
          )}
        </div>

        {activeJob && (
          <p className="mt-4 text-center font-nav text-[12px] text-white/60">
            {isCancellingActiveJob
              ? 'Cancellation is in progress. New assessments stay paused until the current step finishes stopping.'
              : 'A background assessment is already running. New assessments stay paused until it finishes or you cancel it from the banner above.'}
          </p>
        )}
      </div>
    </section>
  );
}

// ─── Purpose Picker ───────────────────────────────────────────────────────
const ARCHETYPES_BY_FAMILY = {
  baseline: [
    { id: '', label: 'Baseline data quality' },
    { id: 'reporting_analytics', label: 'Human reporting & analytics' },
    { id: 'conformed_reference', label: 'Conformed reference / master data' },
  ],
  agent_access: [
    { id: 'mcp_read', label: 'MCP tool access (read)' },
    { id: 'mcp_write', label: 'MCP tool access (read + write)', disabled: true },
    { id: 'nl_query', label: 'Conversational analytics (text-to-SQL)' },
    { id: 'agent_rag', label: 'BI / dashboard agent' },
    { id: 'semantic_search', label: 'RAG / knowledge retrieval' },
    { id: 'time_series_forecast', label: 'Fine-tuning' },
  ],
  model_dev: [
    { id: 'supervised_classification', label: 'Supervised training' },
    { id: 'supervised_regression', label: 'Forecasting / time series' },
    { id: 'feature_store', label: 'Feature store source' },
    { id: 'batch_scoring', label: 'Feature serving / online inference' },
  ],
};

const FAMILY_LABELS = {
  baseline: 'Baseline / DQ',
  agent_access: 'Agent Access / AI',
  model_dev: 'Model Development / ML',
};

function PurposePicker({ selectedPurpose, setSelectedPurpose, semanticScan, setSemanticScan }) {
  return (
    <Card className="mt-6 bg-white/5 border-white/15 p-6">
      <p className="font-nav text-[12px] font-medium text-white/55 mb-4 uppercase tracking-wide">
        What will consume this data?
      </p>

      <div className="space-y-4">
        {Object.entries(ARCHETYPES_BY_FAMILY).map(([family, archetypes]) => (
          <div key={family}>
            <p className="font-nav text-[11px] font-medium text-white/45 uppercase tracking-wide mb-2">
              {FAMILY_LABELS[family]}
            </p>
            <div className="flex flex-wrap gap-2">
              {archetypes.map((arch) => (
                arch.disabled ? (
                  <span
                    key={arch.id}
                    className="px-3 py-1.5 rounded-full text-sm font-medium border border-white/10 bg-white/3 text-white/30 cursor-not-allowed"
                    title="Requires write-safety evidence"
                  >
                    {arch.label}
                  </span>
                ) : (
                  <button
                    key={arch.id}
                    type="button"
                    onClick={() => setSelectedPurpose(arch.id)}
                    className={cn(
                      'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                      selectedPurpose === arch.id
                        ? 'bg-white text-gray-900 shadow-sm ring-2 ring-white/50'
                        : 'border border-white/20 bg-white/5 text-white/80 hover:border-white/40 hover:bg-white/10',
                    )}
                  >
                    {arch.label}
                  </button>
                )
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 pt-4 border-t border-white/10 flex items-center gap-3">
        <Checkbox
          id="semantic-scan"
          checked={semanticScan}
          onCheckedChange={(v) => setSemanticScan(!!v)}
        />
        <Label htmlFor="semantic-scan" className="text-white/70 text-sm cursor-pointer">
          Read values with the language model (semantic scan)
        </Label>
      </div>
    </Card>
  );
}

// ─── CSV panel: drag-drop + file list ──────────────────────────────────────
function CsvPanel({ files, setFiles, metadataFile, setMetadataFile }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = (list) => {
    const next = [...files];
    for (const f of Array.from(list)) {
      if (!f.name.toLowerCase().endsWith('.csv')) continue;
      // Dedupe by name+size
      if (next.find((x) => x.name === f.name && x.size === f.size)) continue;
      next.push(f);
    }
    setFiles(next);
  };

  const removeAt = (i) => setFiles(files.filter((_, idx) => idx !== i));

  return (
    <div className="mt-2">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          'border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all bg-white/5',
          dragOver ? 'border-white/60 bg-white/10' : 'border-white/25 hover:border-white/40',
        )}
      >
        <input
          ref={inputRef} type="file" accept=".csv" multiple className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-white/15 text-white mb-4">
          <Upload className="h-6 w-6" />
        </div>
        <p className="font-display text-2xl font-light text-white mb-2">
          {files.length > 0
            ? `${files.length} file${files.length > 1 ? 's' : ''} ready`
            : 'Drop one or more CSV files here'}
        </p>
        <p className="text-sm text-white/65 max-w-sm mx-auto">
          Click to browse, or drag in. Files are profiled server-side - raw
          rows are discarded after analysis.
        </p>
      </div>

      {files.length > 0 && (
        <ul className="mt-4 space-y-2">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-white/8 border border-white/15"
            >
              <div className="min-w-0 flex-1">
                <p className="text-white font-medium truncate">{f.name}</p>
                <p className="font-nav text-[12px] text-white/55">
                  {(f.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); removeAt(i); }}
                className="text-white/60 hover:text-white p-1.5 rounded-md hover:bg-white/10"
                aria-label={`Remove ${f.name}`}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <MetadataUpload metadataFile={metadataFile} setMetadataFile={setMetadataFile} />
    </div>
  );
}

// ─── DB panel: credential form ─────────────────────────────────────────────
function DbPanel({ credentials, setCredentials, schemaName, setSchemaName, metadataFile, setMetadataFile }) {
  const update = (field) => (e) => {
    const v = e.target.value;
    setCredentials({
      ...credentials,
      [field]: field === 'port' ? parseInt(v || '0', 10) : v,
    });
  };
  const inputClass = 'bg-white/10 border-white/20 text-white placeholder:text-white/40 focus-visible:ring-white/50';
  const labelClass = 'text-white/70';

  return (
    <div className="mt-2 bg-white/5 border border-white/15 rounded-2xl p-6 space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Engine" labelClass={labelClass}>
          <select
            value={credentials.engine}
            onChange={(e) => {
              const eng = e.target.value;
              setCredentials((c) => ({
                ...c,
                engine: eng,
                port: eng === 'redshift' ? 5439 : 5432,
              }));
            }}
            className="flex h-11 w-full rounded-md border bg-white/10 border-white/20 text-white px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
          >
            <option value="postgres">PostgreSQL</option>
            <option value="redshift">Amazon Redshift</option>
          </select>
        </Field>
        <Field label="Host" labelClass={labelClass}>
          <Input value={credentials.host} onChange={update('host')}
                 placeholder="db.internal.lilly.com" className={inputClass} />
        </Field>
        <Field label="Port" labelClass={labelClass}>
          <Input type="number" value={credentials.port} onChange={update('port')} className={inputClass} />
        </Field>
        <Field label="Database" labelClass={labelClass}>
          <Input value={credentials.database} onChange={update('database')}
                 placeholder="analytics_prod" className={inputClass} />
        </Field>
        <Field label="Schema" labelClass={labelClass}>
          <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)}
                 placeholder="public" className={inputClass} />
        </Field>
        <Field label="Username" labelClass={labelClass}>
          <Input value={credentials.username} onChange={update('username')}
                 placeholder="reader" className={inputClass} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Password" labelClass={labelClass}>
            <Input type="password" value={credentials.password} onChange={update('password')}
                   className={inputClass} />
          </Field>
        </div>
      </div>
      <MetadataUpload metadataFile={metadataFile} setMetadataFile={setMetadataFile} />
    </div>
  );
}

function Field({ label, labelClass, children }) {
  return (
    <div className="flex flex-col gap-2">
      <Label className={labelClass}>{label}</Label>
      {children}
    </div>
  );
}

// ─── DB connect button - runs test + listTables, advances on success ───────
function DbConnectButton({ credentials, schemaName, onError, onTablesLoaded }) {
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('idle'); // 'idle' | 'testing' | 'listing'
  const controllerRef = useRef(null);

  const valid = credentials.host && credentials.database && credentials.username
                && credentials.password && schemaName;

  const cancel = () => {
    controllerRef.current?.abort();
    setBusy(false);
    setPhase('idle');
  };

  const handle = async () => {
    if (!valid) return;
    controllerRef.current = new AbortController();
    const { signal } = controllerRef.current;
    setBusy(true);
    setPhase('testing');
    try {
      // 1. Test connection - surfaces fast failures before the table list call
      const test = await api.connectTest(credentials, { signal });
      if (!test.ok) {
        onError({ code: test.code, detail: test.detail });
        return;
      }
      // 2. List tables in the schema
      setPhase('listing');
      const list = await api.listTables(credentials, schemaName, { signal });
      if (!list.tables || list.tables.length === 0) {
        onError({ code: 'NO_TABLES', detail: `Schema "${schemaName}" has no tables.` });
        return;
      }
      onTablesLoaded(list.tables);
    } catch (err) {
      if (err.name === 'AbortError') return; // user cancelled - no error shown
      const ae = err instanceof ApiError ? err : null;
      onError({ code: ae?.code || 'UNKNOWN', detail: ae?.message || String(err) });
    } finally {
      setBusy(false);
      setPhase('idle');
    }
  };

  const phaseLabel = phase === 'testing' ? 'Testing connection…'
                   : phase === 'listing'  ? 'Discovering tables…'
                   : 'Connect & List Tables';

  return (
    <div className="flex items-center gap-2">
      <Button variant="onRed" size="lg" disabled={!valid || busy} onClick={handle}>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {phaseLabel}
        {!busy && <ArrowRight className="h-4 w-4" />}
      </Button>
      {busy && (
        <Button variant="ghostOnRed" size="lg" onClick={cancel}>
          Cancel
        </Button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 2 · Table Selection (DB only)
// ═══════════════════════════════════════════════════════════════════════════
function TableSelection({
  tables,
  selected,
  setSelected,
  activeJob,
  isCancellingActiveJob,
  error,
  onDismissError,
  onBack,
  onResumeActiveJob,
  onRun,
}) {
  const allSelected = selected.size === tables.length;

  const toggle = (name) => {
    const next = new Set(selected);
    next.has(name) ? next.delete(name) : next.add(name);
    setSelected(next);
  };

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(tables.map((t) => t.name)));
  };

  return (
    <section className="container py-20">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <p className="font-nav text-[14px] font-medium text-white/75 mb-4">
            Step 03 · Tables
          </p>
          <h1 className="font-display text-5xl md:text-6xl font-light leading-tight tracking-tight text-white">
            Choose what to assess.
          </h1>
          <p className="mt-4 text-white/75">
            {tables.length} table{tables.length !== 1 ? 's' : ''} found ·{' '}
            {selected.size} selected
          </p>
        </div>

        <div className="bg-white/5 border border-white/15 rounded-2xl overflow-hidden">
          <button
            type="button"
            onClick={toggleAll}
            className="w-full px-5 py-3 flex items-center gap-3 border-b border-white/12 hover:bg-white/5 transition-colors text-left"
          >
            <span className="text-white" onClick={(e) => e.stopPropagation()}>
              <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
            </span>
            <span className="font-nav text-[13px] font-medium text-white">
              {allSelected ? 'Deselect all' : 'Select all'}
            </span>
          </button>
          <ul className="divide-y divide-white/10 max-h-96 overflow-y-auto">
            {tables.map((t) => (
              <li
                key={t.name}
                onClick={() => toggle(t.name)}
                className="px-5 py-3 flex items-center gap-3 hover:bg-white/5 transition-colors cursor-pointer"
              >
                <span className="text-white" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selected.has(t.name)}
                    onCheckedChange={() => toggle(t.name)}
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-white font-medium truncate">{t.name}</p>
                  {(t.column_count > 0 || t.estimated_row_count != null) && (
                    <p className="font-nav text-[12px] text-white/55">
                      {t.column_count > 0 && `${t.column_count} column${t.column_count !== 1 ? 's' : ''}`}
                      {t.column_count > 0 && t.estimated_row_count != null && ' · '}
                      {t.estimated_row_count != null && `~${t.estimated_row_count.toLocaleString()} rows`}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>

        {error && <ErrorBanner error={error} onDismiss={onDismissError} />}

        <div className="mt-10 flex items-center justify-center gap-3">
          <Button variant="ghostOnRed" size="lg" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          {activeJob ? (
            <Button variant="onRed" size="lg" onClick={onResumeActiveJob} disabled={!activeJob.jobId || isCancellingActiveJob}>
              {isCancellingActiveJob
                ? 'Cancelling Assessment'
                : activeJob.jobId
                  ? 'Resume Running Assessment'
                  : 'Preparing Resume Link'}
              {!isCancellingActiveJob && activeJob.jobId && <ArrowRight className="h-4 w-4" />}
            </Button>
          ) : (
            <Button
              variant="onRed" size="lg"
              disabled={selected.size === 0}
              onClick={onRun}
            >
              {`Assess Selected (${selected.size})`}
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>

        {activeJob && (
          <p className="mt-4 text-center font-nav text-[12px] text-white/60">
            {isCancellingActiveJob
              ? 'Cancellation is in progress. New assessments stay paused until the current step finishes stopping.'
              : 'A background assessment is already running. Resume it, cancel it from the banner above, or wait for it to finish before starting another.'}
          </p>
        )}
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 3 · Loading - kick off the job and poll
// ═══════════════════════════════════════════════════════════════════════════

const PROFILE_ACTIONS = [
  'Examining',
  'Investigating',
  'Studying',
  'Scrutinizing',
  'Inspecting',
  'Exploring',
  'Dissecting',
  'Probing',
  'Reviewing',
  'Interpreting',
  'Evaluating',
  'Deconstructing',
  'Parsing',
  'Testing',
  'Diagnosing',
  'Assessing',
  'Researching',
  'Auditing',
  'Scanning',
  'Breaking down',
  'Estimating',
  'Measuring',
  'Grading',
  'Rating',
  'Validating',
  'Verifying',
  'Scoring',
  'Comparing',
  'Benchmarking',
  'Analyzing',
  'Weighing',
  'Qualifying',
  'Determining',
];

const PROFILE_ACTION_INTERVAL_MS = 1900;   // rest time per word
const PROFILE_ACTION_TRANSITION_MS = 520;  // slide + blur duration

function pickProfileAction(excluding) {
  const candidates = PROFILE_ACTIONS.filter((action) => action !== excluding);
  return candidates[Math.floor(Math.random() * candidates.length)];
}


function CyclingProfileAction() {
  // [current, next] - next is staged below, ready to scroll up into focus
  const [[current, next], setPair] = useState(() => {
    const first = pickProfileAction();
    return [first, pickProfileAction(first)];
  });
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    let swapId;
    const tickId = window.setInterval(() => {
      setAnimating(true);
      swapId = window.setTimeout(() => {
        // promote the incoming word to current, stage a fresh next, and
        // turn transitions OFF in the same batch so the reset is instant.
        setPair(([, incoming]) => [incoming, pickProfileAction(incoming)]);
        setAnimating(false);
      }, PROFILE_ACTION_TRANSITION_MS);
    }, PROFILE_ACTION_INTERVAL_MS);

    return () => {
      window.clearInterval(tickId);
      if (swapId) window.clearTimeout(swapId);
    };
  }, []);

  const ease = 'cubic-bezier(0.22, 1, 0.36, 1)';
  const motion = animating
    ? `transform ${PROFILE_ACTION_TRANSITION_MS}ms ${ease},` +
      `opacity ${PROFILE_ACTION_TRANSITION_MS}ms ${ease},` +
      `filter ${PROFILE_ACTION_TRANSITION_MS}ms ${ease}`
    : 'none';

  return (
    <span className="relative inline-block h-[1.15em] min-w-[15ch] overflow-hidden text-center align-baseline">
      {/* outgoing - scrolls up, blurs, fades */}
      <span
        className="absolute inset-0"
        style={{
          transition: motion,
          transform: animating ? 'translateY(-115%)' : 'translateY(0)',
          opacity: animating ? 0 : 1,
          filter: animating ? 'blur(9px)' : 'blur(0px)',
          willChange: 'transform, filter, opacity',
        }}
      >
        {current}
      </span>

      {/* incoming - rises from below, sharpens into focus */}
      <span
        className="absolute inset-0"
        style={{
          transition: motion,
          transform: animating ? 'translateY(0)' : 'translateY(115%)',
          opacity: animating ? 1 : 0,
          filter: animating ? 'blur(0px)' : 'blur(9px)',
          willChange: 'transform, filter, opacity',
        }}
      >
        {next}
      </span>
    </span>
  );
}

function LoadingScreen({
  mode, files, credentials, schemaName, selectedTables,
  metadataFile,
  selectedPurpose,
  semanticScan,
  existingJob,
  activeJob,
  onRunInBackground,
  onCancelJob,
  onComplete,
  onError,
  onJobStarted, onJobUpdated, onJobCleared,
}) {
  const [progress, setProgress] = useState(existingJob?.progress ?? 0);
  const startedRef = useRef(false);
  const cancelledRef = useRef(false);
  const controllerRef = useRef(null);

  useEffect(() => {
    // CRITICAL: reset cancelledRef on every effect run. In React StrictMode
    // dev mode, useEffect runs as: mount → cleanup → mount. The pseudo-
    // cleanup sets cancelledRef.current = true; the immediate re-run resets
    // it to false. This lets the in-flight IIFE proceed normally.
    // On a REAL unmount (user runs it in the background or navigates away),
    // nothing resets it after the cleanup, so the IIFE sees
    // cancelledRef.current = true and bails out.
    cancelledRef.current = false;

    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      let job = existingJob;

      try {
        if (!job?.jobId) {
          job = {
            jobId: null,
            mode,
            status: 'starting',
            progress: 0,
            phase: 'queued',
            sourceLabel: buildActiveJobSummary(mode, files, schemaName, selectedTables),
            createdAt: Date.now(),
          };
          onJobStarted(job);

          const ack = mode === 'csv'
            ? await api.assessCsv(files, metadataFile, { purpose: selectedPurpose })
            : await api.assessDb(credentials, schemaName, [...selectedTables], metadataFile, { purpose: selectedPurpose });

          job = { ...job, jobId: ack.job_id, status: ack.status || 'pending' };
          onJobUpdated(job);
        }

        if (cancelledRef.current) return;

        controllerRef.current = new AbortController();
        const { signal } = controllerRef.current;

        // 2. Poll until done - cooperative cancellation via isCancelled
        const result = await pollJob(job.jobId, {
          intervalMs: 2000,
          signal,
          onProgress: (p, status, phase) => {
            if (cancelledRef.current) return;
            setProgress(p);
            job = {
              ...job,
              progress: p,
              status,
              phase,
            };
            onJobUpdated(job);
          },
          isCancelled: () => cancelledRef.current,
        });

        if (cancelledRef.current || result == null) return;
        onJobCleared();
        onComplete(result);
      } catch (err) {
        if (cancelledRef.current) {
          if (!job?.jobId) {
            onJobCleared();
          }
          return;
        }
        if (err.name === 'AbortError') return;
        const ae = err instanceof ApiError ? err : null;
        const preserveActiveJob = Boolean(job?.jobId) && (
          ae?.code === 'NETWORK'
          || ae?.code === 'TOKEN_EXPIRED'
          || [0, 401, 502, 503, 504].includes(ae?.status ?? -1)
        );
        if (!preserveActiveJob) {
          onJobCleared();
        }
        onError({
          code: ae?.code || 'UNKNOWN',
          detail: preserveActiveJob
            ? `${ae?.message || String(err)} The assessment may still be running - return to Assess and use the Resume Assessment banner at the top of that page.`
            : ae?.message || String(err),
          preserveActiveJob,
        });
      }
    })();

    return () => {
      cancelledRef.current = true;
      controllerRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Smooth visual interpolation - fills progressively instead of jumping
  const [displayProgress, setDisplayProgress] = useState(existingJob?.progress ?? 0);
  useEffect(() => {
    if (displayProgress >= progress) return;
    const id = setInterval(() => {
      setDisplayProgress((prev) => {
        const next = prev + 1;
        if (next >= progress) { clearInterval(id); return progress; }
        return next;
      });
    }, 80);
    return () => clearInterval(id);
  }, [progress, displayProgress]);

  return (
    <section className="container flex flex-col items-center justify-center flex-1 py-24 text-center">
      <h2 className="font-display text-4xl md:text-5xl font-light text-white mb-8">
        <CyclingProfileAction />
      </h2>

      {/* Slim progress bar */}
      <div className="w-72 max-w-full h-1 bg-white/15 rounded-full overflow-hidden mb-8">
        <div
          className="h-full bg-white transition-[width] duration-150 ease-linear"
          style={{ width: `${displayProgress}%` }}
        />
      </div>

      {/* Step labels */}
      <ul className="text-left text-sm text-white/70 space-y-1.5 mb-8">
        <li className="flex items-center gap-2">
          <span className="w-4 text-center text-white/50">&#10003;</span>
          Parsing files
        </li>
        <li className="flex items-center gap-2">
          <span className="w-4 text-center text-white/50">&#10003;</span>
          Profiling every column (full scan)
        </li>
        {semanticScan && (
          <li className="flex items-center gap-2">
            <span className="w-4 text-center text-white">&#9673;</span>
            <span className="text-white">Reading values with the language model</span>
          </li>
        )}
        <li className="flex items-center gap-2">
          <span className="w-4 text-center text-white/40">&#9675;</span>
          <span className="text-white/50">Scoring against your purpose</span>
        </li>
      </ul>

      <p className="font-nav text-[12px] text-white/60 mb-6 max-w-lg">
        Leaving this screen does not stop the backend job. Use Run in background to return to Assess and resume later from the banner there. New assessments stay paused until this run finishes.
      </p>

      <div className="flex flex-col sm:flex-row items-center gap-3">
        <Button variant="ghostOnRed" onClick={onRunInBackground}>
          Run in Background
        </Button>
        <Button variant="onRed" onClick={onCancelJob} disabled={!activeJob?.jobId}>
          Cancel Assessment
        </Button>
      </div>
    </section>
  );
}


function ActiveAssessmentBanner({ job, isCancelling, onResume, onCancel }) {
  const statusLabel = job.status === 'starting'
    ? 'Starting'
    : job.status === 'pending'
      ? 'Queued'
      : job.status === 'cancelling'
        ? 'Cancelling'
      : 'Running';
  const phaseLabel = job.phase && job.phase !== job.status
    ? formatJobPhase(job.phase)
    : '';

  return (
    <section className="container pt-6 md:pt-8">
      <div className="max-w-3xl mx-auto rounded-2xl bg-white/10 backdrop-blur-sm border border-white/20 px-5 py-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between shadow-lg">
        <div>
          <p className="font-nav text-[12px] font-medium text-white/65 mb-1">
            Assessment in background
          </p>
          <p className="text-white text-sm md:text-base leading-relaxed">
            {job.sourceLabel || 'A previous assessment'} is {statusLabel.toLowerCase()}
            {phaseLabel ? ` · ${phaseLabel}` : ''}.
          </p>
          <p className="font-nav text-[12px] text-white/50 mt-1">
            {job.progress ?? 0}% complete. This banner stays at the top of Assess while the job keeps running in the backend, and new assessments stay paused until it finishes or cancellation completes.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <Button variant="onRed" size="lg" onClick={onResume} disabled={!job.jobId || isCancelling}>
            {job.jobId ? 'Resume Running Assessment' : 'Preparing Resume Link'}
            {job.jobId && !isCancelling && <ArrowRight className="h-4 w-4" />}
          </Button>
          <Button variant="ghostOnRed" size="lg" onClick={onCancel} disabled={!job.jobId || isCancelling}>
            {isCancelling ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Cancelling Assessment
              </>
            ) : (
              'Cancel Assessment'
            )}
          </Button>
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Shared metadata upload widget
// ═══════════════════════════════════════════════════════════════════════════
function MetadataUpload({ metadataFile, setMetadataFile }) {
  const inputRef = useRef(null);
  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      <p className="font-nav text-[12px] font-medium text-white/55 mb-2 uppercase tracking-wide">
        Data dictionary <span className="normal-case">(optional)</span>
      </p>
      {metadataFile ? (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-white/8 border border-white/15">
          <FileText className="h-4 w-4 text-white/60 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm truncate">{metadataFile.name}</p>
            <p className="font-nav text-[11px] text-white/45">
              {(metadataFile.size / 1024).toFixed(1)} KB
            </p>
          </div>
          <button
            type="button"
            onClick={() => setMetadataFile(null)}
            className="text-white/50 hover:text-white p-1 rounded"
            aria-label="Remove metadata file"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-white/5 border border-dashed border-white/20 hover:border-white/35 hover:bg-white/8 transition-all text-left"
        >
          <input
            ref={inputRef} type="file" accept=".csv" className="hidden"
            onChange={(e) => e.target.files[0] && setMetadataFile(e.target.files[0])}
          />
          <FileText className="h-4 w-4 text-white/40 shrink-0" />
          <div>
            <p className="text-white/65 text-sm">Upload a data dictionary CSV</p>
            <p className="font-nav text-[11px] text-white/35">
              One row per column - column_name, description, pii_classification, business_owner…
            </p>
          </div>
        </button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Inline error banner
// ═══════════════════════════════════════════════════════════════════════════
function ErrorBanner({ error, onDismiss }) {
  return (
    <div className="mt-6 flex items-start gap-3 p-4 rounded-xl bg-white/8 border border-white/20">
      <AlertCircle className="h-5 w-5 text-white shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="font-nav text-[12px] font-medium text-white/65 mb-0.5">
          {error.code || 'Error'}
        </p>
        <p className="text-white text-sm leading-relaxed">{error.detail}</p>
      </div>
      <button
        onClick={onDismiss}
        className="text-white/60 hover:text-white p-1"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
