import { useMemo, useState } from 'react';
import { Download, Plus, Search } from 'lucide-react';
import type { CandidateResult, ScreeningResults } from '../types/results';
import { downloadJson, formatDateTime, pluralize } from '../lib/format';
import { BatchSummary } from './BatchSummary';
import { CandidateDetails } from './CandidateDetails';
import { CandidateTable } from './CandidateTable';
import { EmptyState } from './EmptyState';
import { DuplicatesList, FailedList, RejectedList } from './OtherResults';

type Tab = 'all' | 'eligible' | 'rejected' | 'failed' | 'duplicates';

export const DOWNLOAD_FILENAME = 'resume-screening-results.json';

function matches(query: string, ...fields: (string | null | undefined | string[])[]): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return fields.flat().some((f) => typeof f === 'string' && f.toLowerCase().includes(q));
}

const candidateMatches = (q: string, c: CandidateResult) =>
  matches(q, c.candidate_name, c.resume_filename, c.matched_skills);

export function ResultsView({ results, onReset }: { results: ScreeningResults; onReset: () => void }) {
  const summary = results.batch_summary;
  const [tab, setTab] = useState<Tab>(summary.eligible > 0 ? 'eligible' : 'all');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<CandidateResult | null>(null);

  // UI-only filtering. Order is preserved exactly as the backend returned it.
  const eligible = useMemo(() => results.eligible_candidates.filter((c) => candidateMatches(query, c)), [results, query]);
  const rejected = useMemo(() => results.rejected_candidates.filter((c) => candidateMatches(query, c)), [results, query]);
  const failed = useMemo(() => results.failed_candidates.filter((c) => matches(query, c.resume_filename, c.error?.error_type, c.error?.stage)), [results, query]);
  const duplicates = useMemo(() => results.duplicates.filter((d) => matches(query, d.resume_filename, d.duplicate_of)), [results, query]);

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'all', label: 'All', count: summary.total_resumes },
    { id: 'eligible', label: 'Eligible', count: summary.eligible },
    { id: 'rejected', label: 'Rejected', count: summary.rejected },
    { id: 'failed', label: 'Failed', count: summary.failed },
    { id: 'duplicates', label: 'Duplicates', count: summary.duplicates },
  ];
  const show = (section: Exclude<Tab, 'all'>) => tab === 'all' || tab === section;
  const noMatches = eligible.length + rejected.length + failed.length + duplicates.length === 0;

  return (
    <main className="container results">
      <div className="results-head">
        <div>
          <h1>Resume Screening</h1>
          <p className="muted">
            {pluralize(summary.total_resumes, 'resume')} processed · {formatDateTime(results.generated_at)}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary" onClick={onReset}>
            <Plus size={16} aria-hidden="true" /> Process another batch
          </button>
          <button type="button" className="btn btn-primary" onClick={() => downloadJson(results, DOWNLOAD_FILENAME)}>
            <Download size={16} aria-hidden="true" /> Download JSON
          </button>
        </div>
      </div>

      <BatchSummary summary={summary} />

      <div className="results-grid">
        <aside className="filters" aria-label="Filters">
          <div className="search">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search candidates…"
              aria-label="Search candidates by name, skill or filename"
            />
          </div>
          <nav aria-label="Result groups" className="tabs">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab ${tab === t.id ? 'is-active' : ''}`}
                aria-pressed={tab === t.id}
                onClick={() => setTab(t.id)}
              >
                <span>{t.label}</span>
                <span className="tab-count">{t.count}</span>
              </button>
            ))}
          </nav>
          <p className="muted small filters-note">
            Ranking comes from the screening service. Search and tabs only filter what was returned.
          </p>
        </aside>

        <section className="results-main" aria-live="polite">
          {noMatches && (
            <EmptyState title={query ? `No results match “${query}”` : 'Nothing to show here'}>
              {query ? 'Try a different name, skill or filename.' : 'This batch produced no results in this group.'}
            </EmptyState>
          )}

          {show('eligible') && !noMatches && (tab !== 'all' || eligible.length > 0 || (summary.eligible === 0 && !query)) && (
            <div className="group">
              <div className="group-head">
                <h2>Ranked eligible candidates</h2>
                <span className="muted">Highest score first</span>
              </div>
              {eligible.length > 0 ? (
                <CandidateTable candidates={eligible} onOpen={setOpen} />
              ) : (
                <EmptyState title="No eligible candidates">
                  {summary.eligible === 0 ? 'No resume in this batch met both the Python and AI requirements.' : 'No eligible candidate matches the search.'}
                </EmptyState>
              )}
            </div>
          )}

          {show('rejected') && (tab !== 'all' || rejected.length > 0) && !noMatches && (
            <div className="group">
              <div className="group-head">
                <h2>Rejected candidates</h2>
                <span className="muted">Did not meet the hard eligibility rules</span>
              </div>
              {rejected.length > 0 ? <RejectedList candidates={rejected} onOpen={setOpen} /> : <EmptyState title="No rejected candidates" />}
            </div>
          )}

          {show('failed') && (tab !== 'all' || failed.length > 0) && !noMatches && (
            <div className="group">
              <div className="group-head">
                <h2>Processing failures</h2>
                <span className="muted">Failed is not rejected: these files could not be read, so they were never evaluated</span>
              </div>
              {failed.length > 0 ? <FailedList candidates={failed} /> : <EmptyState title="No processing failures" />}
            </div>
          )}

          {show('duplicates') && (tab !== 'all' || duplicates.length > 0) && !noMatches && (
            <div className="group">
              {duplicates.length > 0 ? (
                <DuplicatesList duplicates={duplicates} defaultOpen={tab === 'duplicates'} />
              ) : (
                <EmptyState title="No duplicates" />
              )}
            </div>
          )}
        </section>
      </div>

      {open && <CandidateDetails candidate={open} onClose={() => setOpen(null)} />}
    </main>
  );
}
