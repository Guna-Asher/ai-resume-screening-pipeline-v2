import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { ScreenOptions } from '../api/client';
import { formatElapsed, pluralize } from '../lib/format';

/**
 * The backend answers one synchronous request and reports no progress, so this is an
 * indeterminate state: no percentages and no ticked-off steps we cannot actually know about.
 */
export function ProcessingState({ count, options, onStop }: { count: number; options: ScreenOptions; onStop: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const stages = [
    'Extracting candidate information',
    'Evaluating Python + AI eligibility',
    ...(options.useLlm ? ['Semantic analysis (if configured)'] : []),
    ...(options.useGithub ? ['Enriching GitHub activity'] : []),
    'Scoring and building the ranking',
  ];

  return (
    <section className="card processing" aria-live="polite" aria-busy="true">
      <Loader2 className="spinner" size={28} aria-hidden="true" />
      <h1>Processing {pluralize(count, 'resume')}…</h1>
      <p className="muted">Your batch is being evaluated. This can take a while for large batches.</p>
      <div className="indeterminate" aria-hidden="true"><span /></div>
      <p className="elapsed mono" aria-label="Elapsed time">{formatElapsed(seconds)}</p>
      <div className="stages">
        <p className="stages-title">What the server does for each batch</p>
        <ol>
          {stages.map((s) => <li key={s}><span className="dot dot-neutral" aria-hidden="true" />{s}</li>)}
        </ol>
        <p className="muted small">The server does not report live progress, so these steps are not ticked off individually.</p>
      </div>
      <button type="button" className="btn btn-ghost" onClick={onStop}>Stop waiting</button>
    </section>
  );
}
