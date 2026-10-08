import { ChevronRight, X } from 'lucide-react';
import type { CandidateResult, DuplicateRecord } from '../types/results';
import { candidateTitle, pluralize } from '../lib/format';
import { SkillChips } from './CandidateCard';
import { StatusBadge } from './StatusBadge';

export function RejectedList({ candidates, onOpen }: { candidates: CandidateResult[]; onOpen: (c: CandidateResult) => void }) {
  return (
    <ul className="stack" aria-label="Rejected candidates">
      {candidates.map((c, i) => (
        <li key={c.resume_hash ?? c.resume_filename} className="enter" style={{ animationDelay: `${Math.min(i, 12) * 35}ms` }}>
          <button type="button" className="candidate candidate-rejected" onClick={() => onOpen(c)} aria-label={`Open details for ${candidateTitle(c)}`}>
            <div className="candidate-top">
              <div className="candidate-id">
                <h3 className="truncate">{candidateTitle(c)}</h3>
                <p className="muted mono truncate">{c.resume_filename}</p>
              </div>
              <StatusBadge tone="bad">Not eligible</StatusBadge>
              <ChevronRight size={18} aria-hidden="true" className="chevron muted" />
            </div>
            <div>
              <p className="field-label">Reasons</p>
              <ul className="reasons">
                {c.rejection_reasons.map((r) => (
                  <li key={r}><X size={14} aria-hidden="true" />{r}</li>
                ))}
              </ul>
            </div>
            <SkillChips skills={c.matched_skills} />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function FailedList({ candidates }: { candidates: CandidateResult[] }) {
  return (
    <ul className="stack" aria-label="Processing failures">
      {candidates.map((c) => (
        <li key={c.resume_filename} className="row-card enter">
          <div className="row-card-top">
            <p className="mono truncate" title={c.resume_filename}>{c.resume_filename}</p>
            <StatusBadge tone="warn">Failed</StatusBadge>
          </div>
          {c.error && (
            <dl className="kv">
              <div><dt>Stage</dt><dd>{c.error.stage}</dd></div>
              <div><dt>Error</dt><dd>{c.error.error_type}</dd></div>
              <div className="kv-wide"><dt>Message</dt><dd>{c.error.message}</dd></div>
            </dl>
          )}
        </li>
      ))}
    </ul>
  );
}

const DUP_REASON = { identical_file: 'identical file', identical_text: 'identical text' } as const;

export function DuplicatesList({ duplicates, defaultOpen }: { duplicates: DuplicateRecord[]; defaultOpen: boolean }) {
  return (
    <details className="card dup" open={defaultOpen}>
      <summary>
        <span className="dup-title">Duplicates</span>
        <span className="muted">{pluralize(duplicates.length, 'file')} skipped</span>
      </summary>
      <ul className="dup-list">
        {duplicates.map((d) => (
          <li key={d.resume_filename}>
            <span className="mono truncate" title={d.resume_filename}>{d.resume_filename}</span>
            <span className="muted">duplicate of</span>
            <span className="mono truncate" title={d.duplicate_of}>{d.duplicate_of}</span>
            <StatusBadge tone="neutral">{DUP_REASON[d.reason] ?? d.reason}</StatusBadge>
          </li>
        ))}
      </ul>
    </details>
  );
}
