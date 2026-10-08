import { AlertTriangle, Check, ChevronRight } from 'lucide-react';
import type { CandidateResult, ProjectSummary } from '../types/results';
import { candidateTitle } from '../lib/format';
import { ScoreBreakdown } from './ScoreBreakdown';

/** The project the backend scored highest, used only to pick which summary to show. */
export function topProject(c: CandidateResult): ProjectSummary | undefined {
  return c.project_summary.reduce<ProjectSummary | undefined>(
    (best, p) => (!best || (p.ai_depth_points ?? -1) > (best.ai_depth_points ?? -1) ? p : best),
    undefined,
  );
}

export function SkillChips({ skills, limit = 8 }: { skills: string[]; limit?: number }) {
  if (skills.length === 0) return null;
  return (
    <ul className="chips" aria-label="Matched skills">
      {skills.slice(0, limit).map((s) => <li key={s} className="chip">{s}</li>)}
      {skills.length > limit && <li className="chip chip-more">+{skills.length - limit}</li>}
    </ul>
  );
}

export function CandidateCard({ candidate, index, onOpen }: { candidate: CandidateResult; index: number; onOpen: () => void }) {
  const score = candidate.score_breakdown;
  const project = topProject(candidate);
  const summary = project ? project.semantic_summary || project.description : null;
  const total = score ? Object.values(score.category_max).reduce((a, b) => a + b, 0) : 100;

  return (
    <li className="enter" style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
      <button type="button" className="candidate" onClick={onOpen} aria-label={`Open details for ${candidateTitle(candidate)}`}>
        <div className="candidate-top">
          <span className={`rank ${candidate.rank !== null && candidate.rank <= 3 ? 'rank-top' : ''}`} aria-label={`Rank ${candidate.rank}`}>
            #{candidate.rank}
          </span>
          <div className="candidate-id">
            <h3 className="truncate">{candidateTitle(candidate)}</h3>
            <p className="muted mono truncate">{candidate.resume_filename}</p>
          </div>
          <div className="candidate-score" aria-label={`Total score ${score?.total_score} out of ${total}`}>
            <span className="score-big">{score?.total_score}</span>
            <span className="muted"> / {total}</span>
          </div>
          <ChevronRight size={18} aria-hidden="true" className="chevron muted" />
        </div>

        {project && (
          <div className="candidate-project">
            <p className="project-name">{project.name}{project.shallow ? <span className="badge badge-warn">Shallow wrapper</span> : null}</p>
            {summary && <p className="project-summary">{summary}</p>}
          </div>
        )}

        {score && <ScoreBreakdown score={score} compact />}

        <SkillChips skills={candidate.matched_skills} />

        {(candidate.strengths.length > 0 || candidate.concerns.length > 0) && (
          <div className="sc">
            {candidate.strengths.slice(0, 2).map((s) => (
              <p className="sc-line sc-good" key={s}><Check size={14} aria-hidden="true" />{s}</p>
            ))}
            {candidate.concerns.length > 0 && (
              <p className="sc-line sc-warn">
                <AlertTriangle size={14} aria-hidden="true" />
                {candidate.concerns.length === 1 ? candidate.concerns[0] : `${candidate.concerns.length} concerns, see details`}
              </p>
            )}
          </div>
        )}
      </button>
    </li>
  );
}
