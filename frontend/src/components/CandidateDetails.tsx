import { useState } from 'react';
import { Check, AlertTriangle, ExternalLink, X, Copy } from 'lucide-react';
import type { CandidateResult, Evidence, GitHubEnrichment } from '../types/results';
import { GITHUB_STATUS_TEXT, candidateTitle, copyText, safeGithubUrl } from '../lib/format';
import { useDialog } from '../hooks/useDialog';
import { SkillChips } from './CandidateCard';
import { ScoreBreakdown } from './ScoreBreakdown';
import { StatusBadge } from './StatusBadge';

function EvidenceLine({ e }: { e: Evidence }) {
  return (
    <li className="evidence-line">
      <q>{e.text}</q>
      <span className="muted small">
        {e.source}{e.context ? ` · ${e.context}` : ''}
        {e.origin === 'llm' && <StatusBadge tone="accent" title="Detected by the optional LLM analysis, grounded in this resume text">LLM</StatusBadge>}
        {e.note && <span> · {e.note}</span>}
      </span>
    </li>
  );
}

function GitHubPanel({ github }: { github: GitHubEnrichment }) {
  const ok = github.status === 'ok';
  const profile = safeGithubUrl(github.profile_url);
  return (
    <section className="detail-section" aria-labelledby="gh-title">
      <h3 id="gh-title">GitHub</h3>
      {ok ? (
        <>
          <p className="gh-score">
            <span className="score-big">{github.total_points}</span><span className="muted"> / 10</span>
            <span className="muted small"> · recent activity {github.recent_activity_points}/5 · repositories {github.repository_points}/5</span>
          </p>
          {github.summary && <p>{github.summary}</p>}
          {github.evidence.length > 0 && (
            <ul className="bullets small">{github.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
          )}
          {github.relevant_repositories.length > 0 && (
            <ul className="repos">
              {github.relevant_repositories.map((r) => {
                const url = safeGithubUrl(r.html_url);
                return (
                  <li key={r.name}>
                    {url ? <a href={url} target="_blank" rel="noopener noreferrer">{r.name}</a> : <span>{r.name}</span>}
                    {r.language && <span className="muted small"> · {r.language}</span>}
                    <span className="chips-inline">{r.relevance.map((t) => <span className="chip" key={t}>{t}</span>)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      ) : (
        <>
          <p className="gh-na">{GITHUB_STATUS_TEXT[github.status]}</p>
          <p className="muted small">GitHub is an extra 10-point signal. This does not affect eligibility.</p>
        </>
      )}
      {profile && (
        <a className="ext-link" href={profile} target="_blank" rel="noopener noreferrer">
          {profile.replace('https://', '')} <ExternalLink size={13} aria-hidden="true" />
        </a>
      )}
    </section>
  );
}

export function CandidateDetails({ candidate, onClose }: { candidate: CandidateResult; onClose: () => void }) {
  const ref = useDialog(true, onClose);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');
  const score = candidate.score_breakdown;
  const max = score ? Object.values(score.category_max).reduce((a, b) => a + b, 0) : 0;
  const json = jsonOpen ? JSON.stringify(candidate, null, 2) : '';
  const ledger = score ? score.score_evidence.filter((i) => i.points > 0) : [];
  const found = candidate.eligibility ? [...candidate.eligibility.python_evidence, ...candidate.eligibility.ai_evidence] : [];

  const copy = async () => {
    setCopied((await copyText(JSON.stringify(candidate, null, 2))) ? 'ok' : 'fail');
    setTimeout(() => setCopied('idle'), 2000);
  };

  return (
    <div className="drawer-root">
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="details-title" ref={ref}>
        <header className="drawer-head">
          <div className="drawer-id">
            <p className="eyebrow">
              {candidate.eligible ? <StatusBadge tone="good">Eligible · rank #{candidate.rank}</StatusBadge> : <StatusBadge tone="bad">Not eligible</StatusBadge>}
            </p>
            <h2 id="details-title">{candidateTitle(candidate)}</h2>
            <p className="muted mono small">{candidate.resume_filename}</p>
            {candidate.email && <p className="small">{candidate.email}</p>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close details" data-autofocus>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="drawer-body">
          {score && (
            <section className="detail-section" aria-labelledby="score-title">
              <h3 id="score-title" className="sr-only">Score</h3>
              <p className="hero-score" aria-label={`Total score ${score.total_score} out of ${max}`}>
                <span className="score-huge">{score.total_score}</span><span className="muted"> / {max}</span>
              </p>
              <ScoreBreakdown score={score} />
              {score.penalties.map((p) => (
                <div className="penalty" key={p.code}>
                  <p><strong>Project-quality penalty</strong> <span className="penalty-amount">−{p.amount}</span></p>
                  <p className="small">{p.reason}</p>
                  {p.evidence.length > 0 && <ul className="evidence">{p.evidence.map((e, i) => <EvidenceLine e={e} key={i} />)}</ul>}
                </div>
              ))}
            </section>
          )}

          {!candidate.eligible && candidate.rejection_reasons.length > 0 && (
            <section className="detail-section">
              <h3>Why this candidate is not eligible</h3>
              <ul className="reasons">
                {candidate.rejection_reasons.map((r) => <li key={r}><X size={14} aria-hidden="true" />{r}</li>)}
              </ul>
            </section>
          )}

          {candidate.eligible && <GitHubPanel github={candidate.github_enrichment} />}

          {candidate.matched_skills.length > 0 && (
            <section className="detail-section">
              <h3>Matched skills</h3>
              <SkillChips skills={candidate.matched_skills} limit={40} />
            </section>
          )}

          {candidate.project_summary.length > 0 && (
            <section className="detail-section">
              <h3>Projects</h3>
              <ul className="stack">
                {candidate.project_summary.map((p) => (
                  <li key={p.name} className="project">
                    <p className="project-name">
                      {p.name}
                      {p.ai_depth_points !== null && <span className="badge badge-neutral">AI depth {p.ai_depth_points}</span>}
                      {p.shallow && <span className="badge badge-warn">Shallow wrapper</span>}
                    </p>
                    <p className="small">{p.semantic_summary || p.description}</p>
                    {p.ai_signals.length > 0 && (
                      <p className="chips-inline">{p.ai_signals.map((s) => <span className="chip" key={s}>{s.replace(/_/g, ' ')}</span>)}</p>
                    )}
                    {p.technologies.length > 0 && <p className="muted small">{p.technologies.join(' · ')}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {candidate.strengths.length > 0 && (
            <section className="detail-section">
              <h3>Strengths</h3>
              <ul className="sc">{candidate.strengths.map((s) => <li className="sc-line sc-good" key={s}><Check size={14} aria-hidden="true" />{s}</li>)}</ul>
            </section>
          )}

          {candidate.concerns.length > 0 && (
            <section className="detail-section">
              <h3>Concerns</h3>
              <ul className="sc">{candidate.concerns.map((s) => <li className="sc-line sc-warn" key={s}><AlertTriangle size={14} aria-hidden="true" />{s}</li>)}</ul>
            </section>
          )}

          {ledger.length > 0 && (
            <details className="detail-section fold">
              <summary>Score evidence <span className="muted">({ledger.length} scoring signals)</span></summary>
              <ul className="stack">
                {ledger.map((item) => (
                  <li key={`${item.category}-${item.signal}`} className="ledger">
                    <p><span className="badge badge-good">+{item.points} / {item.max_points}</span> <span className="small">{item.explanation}</span></p>
                    {item.evidence.length > 0 && <ul className="evidence">{item.evidence.map((e, i) => <EvidenceLine e={e} key={i} />)}</ul>}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {!candidate.eligible && found.length > 0 && (
            <details className="detail-section fold">
              <summary>What was found in the resume <span className="muted">({found.length})</span></summary>
              <ul className="evidence">{found.map((e, i) => <EvidenceLine e={e} key={i} />)}</ul>
            </details>
          )}

          {candidate.eligible && candidate.llm_enrichment.status !== 'skipped' && (
            <section className="detail-section">
              <h3>Semantic analysis</h3>
              <p className="small">
                <StatusBadge tone={candidate.llm_enrichment.status === 'ok' ? 'good' : 'neutral'}>{candidate.llm_enrichment.status}</StatusBadge>
                {candidate.llm_enrichment.reason && <span className="muted"> {candidate.llm_enrichment.reason.replace(/_/g, ' ')}</span>}
                {candidate.llm_enrichment.status === 'ok' && <span className="muted"> · {candidate.llm_enrichment.signals_accepted} signals accepted</span>}
              </p>
              {candidate.llm_enrichment.overall_evidence.length > 0 && (
                <ul className="bullets small">{candidate.llm_enrichment.overall_evidence.map((e) => <li key={e}>{e}</li>)}</ul>
              )}
              <p className="muted small">Advisory evidence only. Eligibility and the score are computed deterministically.</p>
            </section>
          )}

          <details className="detail-section fold" onToggle={(e) => setJsonOpen((e.currentTarget as HTMLDetailsElement).open)}>
            <summary>View JSON</summary>
            <div className="json-tools">
              <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
                <Copy size={14} aria-hidden="true" /> Copy JSON
              </button>
              <span className="small muted" role="status">{copied === 'ok' ? 'Copied' : copied === 'fail' ? 'Copy is not available in this browser' : ''}</span>
            </div>
            <pre className="json" tabIndex={0} aria-label="Candidate JSON">{json}</pre>
          </details>
        </div>
      </div>
    </div>
  );
}
