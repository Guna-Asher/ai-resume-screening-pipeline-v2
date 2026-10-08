// Pure display helpers. Nothing here computes screening results.
import type { CandidateResult, CategoryKey, GitHubStatus } from '../types/results';

export const CATEGORY_ORDER: CategoryKey[] = [
  'ai_project_depth',
  'python_backend',
  'cloud_fullstack',
  'github',
  'engineering_depth',
];

export const CATEGORY_LABEL: Record<CategoryKey, string> = {
  ai_project_depth: 'AI / Agentic / RAG',
  python_backend: 'Python & Backend',
  cloud_fullstack: 'Cloud / Full Stack',
  github: 'GitHub',
  engineering_depth: 'Engineering Depth',
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function candidateTitle(c: Pick<CandidateResult, 'candidate_name' | 'resume_filename'>): string {
  return c.candidate_name?.trim() || 'Unnamed candidate';
}

/** Only ever link to real github.com URLs (the value comes from resume text). */
export function safeGithubUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return /^https:\/\/github\.com\/[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)?\/?$/.test(url) ? url : null;
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export const GITHUB_STATUS_TEXT: Record<GitHubStatus, string> = {
  ok: 'Public GitHub activity evaluated',
  missing: 'Not available: no GitHub link on the resume',
  invalid_url: 'Not available: the GitHub link could not be used',
  not_found: 'Unavailable: GitHub profile not found',
  rate_limited: 'Unavailable: GitHub API rate limited',
  timeout: 'Unavailable: GitHub API timed out',
  api_error: 'Unavailable: GitHub API error',
  not_evaluated: 'Not evaluated',
};

export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
