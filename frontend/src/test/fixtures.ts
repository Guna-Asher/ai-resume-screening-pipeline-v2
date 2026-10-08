// Hand-written responses shaped exactly like the backend's ScreeningResults. No logic.
import type { ApiClient } from '../api/client';
import type {
  CandidateResult, DuplicateRecord, GitHubEnrichment, ScoreBreakdown, ScreeningResults,
} from '../types/results';
import { vi } from 'vitest';

export const CATEGORY_MAX = {
  ai_project_depth: 40, python_backend: 30, cloud_fullstack: 15, github: 10, engineering_depth: 5,
} as const;

export function github(over: Partial<GitHubEnrichment> = {}): GitHubEnrichment {
  return {
    status: 'ok', reason: null, profile_url: 'https://github.com/janedoe', username: 'janedoe',
    recent_activity_points: 5, repository_points: 5, total_points: 10,
    public_repositories: 4, maintained_repositories: 3, recent_engineering_events: 30,
    relevant_repositories: [
      { name: 'rag-service', language: 'Python', relevance: ['python', 'rag'], updated_at: '2026-09-01T00:00:00+00:00', html_url: 'https://github.com/janedoe/rag-service' },
    ],
    summary: '30 recent public engineering events; 3 maintained public repositories. Approximate public signal only.',
    evidence: ['30 engineering-related public events in the last 90 days -> 5/5'],
    ...over,
  };
}

export function score(over: Partial<ScoreBreakdown> = {}): ScoreBreakdown {
  return {
    category_max: { ...CATEGORY_MAX },
    ai_project_depth: 36, python_backend: 27, cloud_fullstack: 13, github: 10, github_status: 'ok',
    engineering_depth: 5, penalties: [], total_score: 91,
    score_evidence: [
      {
        category: 'ai_project_depth', signal: 'best_ai_unit', points: 36, max_points: 40,
        explanation: "'Research Assistant Agent': baseline 5 for AI usage + retrieval + agents",
        evidence: [{ category: 'ai_technique', term: 'RAG', text: 'Built a RAG pipeline with embeddings', source: 'project', strength: 'strong', context: 'Research Assistant Agent', note: null, origin: 'rules' }],
      },
      { category: 'github', signal: 'recent_activity', points: 5, max_points: 5, explanation: 'GitHub: recent public engineering activity', evidence: [] },
    ],
    ...over,
  };
}

export function eligible(name: string, rank: number, total: number, over: Partial<CandidateResult> = {}): CandidateResult {
  const slug = name.toLowerCase().replace(/\s+/g, '_');
  return {
    rank, resume_filename: `${slug}.pdf`, resume_hash: `hash-${slug}`, candidate_name: name,
    email: `${slug}@example.com`, github_url: 'https://github.com/janedoe', status: 'ok', error: null,
    eligible: true, rejection_reasons: [], matched_skills: ['Python', 'FastAPI', 'LangGraph', 'RAG'],
    eligibility: null,
    project_summary: [{
      name: 'Research Assistant Agent', description: 'Built a stateful agentic workflow with retrieval and tool calling',
      technologies: ['Python', 'FastAPI'], ai_signals: ['retrieval', 'agents'], ai_depth_points: 30,
      shallow: false, semantic_summary: null, semantic_depth: null, semantic_shallow_wrapper: null,
    }],
    score_breakdown: score({ total_score: total }),
    github_enrichment: github(),
    llm_enrichment: { status: 'skipped', reason: 'llm_disabled', model: null, signals_accepted: 0, rejected_signals: {}, overall_evidence: [], confidence_notes: [] },
    strengths: ['AI depth in Research Assistant Agent: retrieval, agents', 'Python web backend in projects'],
    concerns: ['No cloud, container or deployment evidence', 'No engineering-depth signals'],
    ...over,
  };
}

export function rejected(name: string, reasons: string[], over: Partial<CandidateResult> = {}): CandidateResult {
  const slug = name.toLowerCase().replace(/\s+/g, '_');
  return {
    ...eligible(name, 1, 0), rank: null, eligible: false, score_breakdown: null, strengths: [], concerns: [],
    resume_filename: `${slug}.pdf`, resume_hash: `hash-${slug}`, matched_skills: ['Java', 'React'],
    rejection_reasons: reasons, project_summary: [], github_enrichment: github({ status: 'not_evaluated', total_points: 0, summary: null, evidence: [], relevant_repositories: [] }),
    eligibility: {
      eligible: false, python_passed: false, ai_passed: true, python_evidence: [], matched_skills: ['Java'],
      ai_evidence: [{ category: 'ai_technique', term: 'RAG', text: 'Built a RAG pipeline in Java', source: 'project', strength: 'strong', context: 'Smart Search', note: null, origin: 'rules' }],
      rejection_reasons: reasons,
    },
    ...over,
  };
}

export function failed(filename: string, stage = 'parse', type = 'ResumeParseError', message = 'Could not parse PDF'): CandidateResult {
  return {
    ...eligible('x', 1, 0), rank: null, eligible: false, status: 'failed', score_breakdown: null,
    candidate_name: null, email: null, github_url: null, resume_filename: filename, resume_hash: null,
    matched_skills: [], strengths: [], concerns: [], project_summary: [], eligibility: null,
    error: { stage, error_type: type, message },
  };
}

export const DUPLICATES: DuplicateRecord[] = [
  { resume_filename: 'jane_copy.pdf', duplicate_of: 'jane_doe.pdf', reason: 'identical_file' },
  { resume_filename: 'sam_again.pdf', duplicate_of: 'sam_lee.pdf', reason: 'identical_text' },
];

// total 9 = parsed 5 + failed 2 + duplicates 2 ; parsed 5 = eligible 2 + rejected 3
export function results(over: Partial<ScreeningResults> = {}): ScreeningResults {
  return {
    schema_version: '1.0', generated_at: '2026-10-08T12:00:00Z',
    batch_summary: {
      total_resumes: 9, successfully_parsed: 5, eligible: 2, rejected: 3, failed: 2, duplicates: 2,
      llm_status_counts: { skipped: 5 }, github_status_counts: { ok: 2, not_evaluated: 3 },
    },
    eligible_candidates: [eligible('Jane Doe', 1, 91), eligible('Sam Lee', 2, 64, { matched_skills: ['Python', 'Django'] })],
    rejected_candidates: [
      rejected('Asha Rao', ['No Python evidence found: Python in skills, a project, or work/internship experience.']),
      rejected('Tom Baker', ['Only weak Python mentions found, not genuine evidence.']),
      rejected('Nina Park', ['No AI/LLM/RAG/agentic evidence found.']),
    ],
    failed_candidates: [failed('corrupt.pdf'), failed('notes.docx', 'read', 'UnsupportedFormatError', 'Unsupported file type')],
    duplicates: DUPLICATES,
    ...over,
  };
}

export function makeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    baseUrl: 'http://api.test',
    health: vi.fn().mockResolvedValue(undefined),
    results: vi.fn().mockResolvedValue(null),
    screen: vi.fn().mockResolvedValue(results()),
    ...over,
  };
}

export function pdf(name: string, size = 2048, relativePath?: string): File {
  const file = new File([new Uint8Array(size)], name, { type: 'application/pdf' });
  if (relativePath) Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
}
