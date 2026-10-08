import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, defaultApi } from './api/client';
import type { ApiClient, ScreenOptions } from './api/client';
import type { ScreeningResults } from './types/results';
import { addFiles } from './lib/files';
import type { SelectedFile } from './lib/files';
import { formatDateTime } from './lib/format';
import { Banner } from './components/Banner';
import { Header } from './components/Header';
import type { HealthState } from './components/Header';
import { ProcessingState } from './components/ProcessingState';
import { ResultsView } from './components/ResultsView';
import { UploadPanel } from './components/UploadPanel';

type Phase = 'upload' | 'processing' | 'results';

const HEALTH_RETRY_MS = 10_000;

export default function App({ api = defaultApi }: { api?: ApiClient }) {
  const [health, setHealth] = useState<HealthState>('checking');
  const [phase, setPhase] = useState<Phase>('upload');
  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [notices, setNotices] = useState<string[]>([]);
  const [options, setOptions] = useState<ScreenOptions>({ useLlm: true, useGithub: true });
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ScreeningResults | null>(null);
  const [latest, setLatest] = useState<ScreeningResults | null>(null);
  const [stopped, setStopped] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const processedCount = useRef(0);

  const checkHealth = useCallback(async () => {
    setHealth('checking');
    try {
      await api.health();
      setHealth('connected');
    } catch {
      setHealth('unavailable');
    }
  }, [api]);

  useEffect(() => { void checkHealth(); }, [checkHealth]);

  // Poll only while the backend is down; stop as soon as it answers.
  useEffect(() => {
    if (health !== 'unavailable') return;
    const timer = setInterval(() => void checkHealth(), HEALTH_RETRY_MS);
    return () => clearInterval(timer);
  }, [health, checkHealth]);

  // Once connected, see whether a previous run exists (offered, not forced).
  useEffect(() => {
    if (health !== 'connected') return;
    let cancelled = false;
    api.results().then((r) => { if (!cancelled) setLatest(r); }).catch(() => { if (!cancelled) setLatest(null); });
    return () => { cancelled = true; };
  }, [health, api]);

  const addSelected = (incoming: File[]) => {
    const { accepted, notices: added } = addFiles(files, incoming);
    if (accepted.length) setFiles((current) => [...current, ...accepted]);
    setNotices(added);
    setError(null);
  };

  const process = async () => {
    if (files.length === 0 || phase === 'processing') return;
    const abort = new AbortController();
    controller.current = abort;
    processedCount.current = files.length;
    setError(null);
    setStopped(false);
    setPhase('processing');
    try {
      const data = await api.screen(files, options, abort.signal);
      setResults(data);
      setLatest(data);
      setPhase('results');
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'aborted') {
        setStopped(true);
      } else {
        setError(err instanceof ApiError ? err.message : 'Something went wrong while processing. Please try again.');
        if (err instanceof ApiError && err.kind === 'offline') setHealth('unavailable');
      }
      setPhase('upload'); // files stay selected
    } finally {
      controller.current = null;
    }
  };

  const reset = () => {
    setResults(null);
    setFiles([]);
    setNotices([]);
    setError(null);
    setStopped(false);
    setPhase('upload');
  };

  const disabledReason =
    files.length === 0
      ? 'Select at least one resume PDF to begin.'
      : health === 'unavailable'
        ? 'The backend is unavailable. Start it and retry before processing.'
        : null;

  return (
    <>
      <Header health={health} baseUrl={api.baseUrl} onRetry={() => void checkHealth()} />
      {phase === 'results' && results ? (
        <ResultsView results={results} onReset={reset} />
      ) : (
        <main className="container narrow">
          {health === 'unavailable' && (
            <Banner
              tone="error"
              title="Backend unavailable"
              actions={<button type="button" className="btn btn-secondary btn-sm" onClick={() => void checkHealth()}>Retry</button>}
            >
              Cannot reach the screening service at {api.baseUrl}. Start it with <code>docker compose up</code> and check that CORS allows this page.
            </Banner>
          )}
          {error && (
            <Banner
              tone="error"
              title="Processing failed"
              actions={
                <>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => void process()}>Try Again</button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setError(null)}>Dismiss</button>
                </>
              }
            >
              {error}
            </Banner>
          )}
          {stopped && (
            <Banner tone="info" title="Stopped waiting">
              The request was cancelled in this browser, but the server may still finish the batch. Check “View latest results” in a moment.
            </Banner>
          )}
          {phase === 'upload' && latest && (
            <Banner
              tone="info"
              title="Previous screening results available"
              actions={
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setResults(latest); setPhase('results'); }}>
                  View latest results
                </button>
              }
            >
              Generated {formatDateTime(latest.generated_at)} · {latest.batch_summary.eligible} eligible of {latest.batch_summary.total_resumes} resumes.
            </Banner>
          )}
          {phase === 'processing' ? (
            <ProcessingState count={processedCount.current} options={options} onStop={() => controller.current?.abort()} />
          ) : (
            <UploadPanel
              files={files}
              notices={notices}
              options={options}
              disabledReason={disabledReason}
              onAddFiles={addSelected}
              onRemove={(id) => setFiles((current) => current.filter((f) => f.id !== id))}
              onClear={() => { setFiles([]); setNotices([]); }}
              onDismissNotices={() => setNotices([])}
              onOptionsChange={setOptions}
              onProcess={() => void process()}
            />
          )}
        </main>
      )}
    </>
  );
}
