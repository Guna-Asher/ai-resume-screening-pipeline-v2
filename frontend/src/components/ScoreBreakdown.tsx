import type { ScoreBreakdown as Score } from '../types/results';
import { CATEGORY_LABEL, CATEGORY_ORDER } from '../lib/format';

/** Renders the backend's category points against the backend's category maxima. No maths of our own. */
export function ScoreBreakdown({ score, compact = false }: { score: Score; compact?: boolean }) {
  return (
    <div className={`scores ${compact ? 'scores-compact' : ''}`}>
      {CATEGORY_ORDER.map((key, i) => {
        const points = score[key];
        const max = score.category_max[key];
        const unavailable = key === 'github' && score.github_status !== 'ok';
        return (
          <div className="score-row" key={key}>
            <span className="score-label">{CATEGORY_LABEL[key]}</span>
            <div
              className={`bar ${unavailable ? 'bar-na' : ''}`}
              role="meter"
              aria-label={`${CATEGORY_LABEL[key]}: ${points} of ${max}`}
              aria-valuemin={0}
              aria-valuemax={max}
              aria-valuenow={points}
            >
              <span style={{ width: `${max > 0 ? (points / max) * 100 : 0}%`, animationDelay: `${i * 60}ms` }} />
            </div>
            <span className="score-val">
              {points}
              <span className="muted"> / {max}</span>
            </span>
          </div>
        );
      })}
      {score.penalties.map((p) => (
        <div className="score-row score-penalty" key={p.code}>
          <span className="score-label">Project-quality penalty</span>
          <span className="penalty-line" aria-hidden="true" />
          <span className="score-val">−{p.amount}</span>
        </div>
      ))}
    </div>
  );
}
