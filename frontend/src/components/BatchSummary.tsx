import type { BatchSummary as Summary } from '../types/results';

interface Segment {
  key: string;
  label: string;
  value: number;
  tone: string;
}

/** Tiny SVG ring: segment lengths are the backend's numbers, nothing else. */
function Distribution({ summary }: { summary: Summary }) {
  const segments: Segment[] = [
    { key: 'eligible', label: 'Eligible', value: summary.eligible, tone: 'good' },
    { key: 'rejected', label: 'Rejected', value: summary.rejected, tone: 'bad' },
    { key: 'failed', label: 'Failed', value: summary.failed, tone: 'warn' },
    { key: 'duplicates', label: 'Duplicates', value: summary.duplicates, tone: 'neutral' },
  ];
  const sum = segments.reduce((n, s) => n + s.value, 0);
  const label = segments.map((s) => `${s.label} ${s.value}`).join(', ');
  let offset = 0;
  return (
    <div className="dist">
      <svg viewBox="0 0 36 36" className="ring" role="img" aria-label={`Batch outcome: ${label}`}>
        <circle cx="18" cy="18" r="15.9155" className="ring-track" />
        {sum > 0 &&
          segments
            .filter((s) => s.value > 0)
            .map((s) => {
              const length = (s.value / sum) * 100;
              const el = (
                <circle
                  key={s.key}
                  cx="18"
                  cy="18"
                  r="15.9155"
                  className={`ring-seg ring-${s.tone}`}
                  strokeDasharray={`${Math.max(length - (segments.filter((x) => x.value > 0).length > 1 ? 0.8 : 0), 0.1)} ${100 - length}`}
                  strokeDashoffset={-offset}
                />
              );
              offset += length;
              return el;
            })}
        <text x="18" y="17.5" className="ring-num" textAnchor="middle">
          {summary.total_resumes}
        </text>
        <text x="18" y="22.5" className="ring-cap" textAnchor="middle">
          resumes
        </text>
      </svg>
      <ul className="legend">
        {segments.map((s) => (
          <li key={s.key}>
            <span className={`dot dot-${s.tone}`} aria-hidden="true" />
            <span>{s.label}</span>
            <span className="legend-val">{s.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const STATS: { key: keyof Summary; label: string; note: string; tone?: string }[] = [
  { key: 'total_resumes', label: 'Total resumes', note: 'files in this batch' },
  { key: 'successfully_parsed', label: 'Successfully parsed', note: 'read and screened' },
  { key: 'eligible', label: 'Eligible', note: 'Python + AI evidence', tone: 'good' },
  { key: 'rejected', label: 'Rejected', note: 'failed the hard filter', tone: 'bad' },
  { key: 'failed', label: 'Failed', note: 'could not be processed', tone: 'warn' },
  { key: 'duplicates', label: 'Duplicates', note: 'skipped', tone: 'neutral' },
];

function countsText(counts: Record<string, number>): string {
  const entries = Object.entries(counts);
  return entries.length ? entries.map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(' · ') : 'none';
}

export function BatchSummary({ summary }: { summary: Summary }) {
  return (
    <section aria-label="Batch summary" className="summary">
      <div className="stats">
        {STATS.map((s) => (
          <div className={`stat ${s.tone ? `stat-${s.tone}` : ''}`} key={s.key}>
            <p className="stat-label">{s.label}</p>
            <p className="stat-value">{summary[s.key] as number}</p>
            <p className="stat-note">{s.note}</p>
          </div>
        ))}
      </div>
      <div className="card dist-card">
        <Distribution summary={summary} />
        <dl className="enrich">
          <div>
            <dt>LLM analysis</dt>
            <dd>{countsText(summary.llm_status_counts)}</dd>
          </div>
          <div>
            <dt>GitHub enrichment</dt>
            <dd>{countsText(summary.github_status_counts)}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
