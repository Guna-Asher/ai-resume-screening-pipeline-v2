import type { CandidateResult } from '../types/results';
import { CandidateCard } from './CandidateCard';

/** Eligible candidates in exactly the order the backend returned them (its ranking is authoritative). */
export function CandidateTable({ candidates, onOpen }: { candidates: CandidateResult[]; onOpen: (c: CandidateResult) => void }) {
  return (
    <ol className="candidate-list" aria-label="Ranked eligible candidates">
      {candidates.map((c, i) => (
        <CandidateCard key={c.resume_hash ?? c.resume_filename} candidate={c} index={i} onOpen={() => onOpen(c)} />
      ))}
    </ol>
  );
}
