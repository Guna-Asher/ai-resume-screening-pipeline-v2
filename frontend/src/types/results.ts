// Mirrors the backend's canonical Pydantic models (backend/app/models/results.py and friends).
// These are *display* types: the frontend never computes, re-ranks or re-scores anything.

export type EvidenceSource =
  | 'header' | 'summary' | 'skills' | 'project' | 'experience' | 'education' | 'certifications' | 'other';

export interface Evidence {
  category: string;
  term: string;
  text: string;
  source: EvidenceSource;
  strength: 'weak' | 'moderate' | 'strong';
  context: string | null;
  note: string | null;
  origin: 'rules' | 'llm';
}

export type CategoryKey =
  | 'ai_project_depth' | 'python_backend' | 'cloud_fullstack' | 'github' | 'engineering_depth';

export interface ScoreItem {
  category: CategoryKey;
  signal: string;
  points: number;
  max_points: number;
  explanation: string;
  evidence: Evidence[];
}

export interface Penalty {
  code: string;
  amount: number;
  reason: string;
  evidence: Evidence[];
}

export type GitHubStatus =
  | 'not_evaluated' | 'missing' | 'invalid_url' | 'ok' | 'not_found'
  | 'rate_limited' | 'timeout' | 'api_error';

export interface ScoreBreakdown {
  category_max: Record<CategoryKey, number>;
  ai_project_depth: number;
  python_backend: number;
  cloud_fullstack: number;
  github: number;
  github_status: GitHubStatus;
  engineering_depth: number;
  penalties: Penalty[];
  total_score: number;
  score_evidence: ScoreItem[];
}

export interface RelevantRepository {
  name: string;
  language: string | null;
  relevance: string[];
  updated_at: string | null;
  html_url: string | null;
}

export interface GitHubEnrichment {
  status: GitHubStatus;
  reason: string | null;
  profile_url: string | null;
  username: string | null;
  recent_activity_points: number;
  repository_points: number;
  total_points: number;
  public_repositories: number | null;
  maintained_repositories: number | null;
  recent_engineering_events: number | null;
  relevant_repositories: RelevantRepository[];
  summary: string | null;
  evidence: string[];
}

export interface LLMEnrichment {
  status: 'ok' | 'failed' | 'unavailable' | 'skipped';
  reason: string | null;
  model: string | null;
  signals_accepted: number;
  rejected_signals: Record<string, number>;
  overall_evidence: string[];
  confidence_notes: string[];
}

export interface ProjectSummary {
  name: string;
  description: string;
  technologies: string[];
  ai_signals: string[];
  ai_depth_points: number | null;
  shallow: boolean | null;
  semantic_summary: string | null;
  semantic_depth: string | null;
  semantic_shallow_wrapper: boolean | null;
}

export interface EligibilityResult {
  eligible: boolean;
  python_passed: boolean;
  ai_passed: boolean;
  python_evidence: Evidence[];
  ai_evidence: Evidence[];
  matched_skills: string[];
  rejection_reasons: string[];
}

export interface ProcessingError {
  stage: string;
  error_type: string;
  message: string;
}

export interface CandidateResult {
  rank: number | null;
  resume_filename: string;
  resume_hash: string | null;
  candidate_name: string | null;
  email: string | null;
  github_url: string | null;
  status: 'ok' | 'failed';
  error: ProcessingError | null;
  eligible: boolean;
  rejection_reasons: string[];
  matched_skills: string[];
  eligibility: EligibilityResult | null;
  project_summary: ProjectSummary[];
  score_breakdown: ScoreBreakdown | null;
  github_enrichment: GitHubEnrichment;
  llm_enrichment: LLMEnrichment;
  strengths: string[];
  concerns: string[];
}

export interface DuplicateRecord {
  resume_filename: string;
  duplicate_of: string;
  reason: 'identical_file' | 'identical_text';
}

export interface BatchSummary {
  total_resumes: number;
  successfully_parsed: number;
  eligible: number;
  rejected: number;
  failed: number;
  duplicates: number;
  llm_status_counts: Record<string, number>;
  github_status_counts: Record<string, number>;
}

export interface ScreeningResults {
  schema_version: string;
  generated_at: string;
  batch_summary: BatchSummary;
  eligible_candidates: CandidateResult[];
  rejected_candidates: CandidateResult[];
  failed_candidates: CandidateResult[];
  duplicates: DuplicateRecord[];
}
