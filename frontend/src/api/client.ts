// The ONLY module that talks to the backend. Components never call fetch() directly.
import type { ScreeningResults } from '../types/results';

export type ApiErrorKind = 'offline' | 'timeout' | 'aborted' | 'http' | 'invalid_response';

/** An error whose `message` is safe and actionable to show to the user (never a stack trace). */
export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface UploadItem {
  file: File;
  /** Name sent to the server; a folder-relative path when the file came from a folder. */
  name: string;
}

export interface ScreenOptions {
  useLlm: boolean;
  useGithub: boolean;
}

export interface ApiClient {
  readonly baseUrl: string;
  health(): Promise<void>;
  results(): Promise<ScreeningResults | null>;
  screen(items: UploadItem[], options: ScreenOptions, signal?: AbortSignal): Promise<ScreeningResults>;
}

export interface ClientConfig {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  screenTimeoutMs?: number;
  quickTimeoutMs?: number;
}

const DEFAULT_BASE_URL = 'http://localhost:8000';
const DEFAULT_SCREEN_TIMEOUT_MS = 10 * 60 * 1000; // a large batch with an LLM can legitimately take minutes
const DEFAULT_QUICK_TIMEOUT_MS = 8 * 1000;

export function configuredBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL as string | undefined;
  return (fromEnv && fromEnv.trim() ? fromEnv : DEFAULT_BASE_URL).replace(/\/+$/, '');
}

function httpErrorMessage(status: number, detail: unknown): string {
  switch (status) {
    case 400:
      return typeof detail === 'string' && detail.length < 300
        ? detail
        : 'The server could not use the uploaded files.';
    case 409:
      return 'Another screening run is currently in progress. Please try again after it finishes.';
    case 413:
      return 'This batch exceeds the server upload limits. Remove some files or reduce file sizes.';
    case 422:
      return 'The server rejected the request: no valid resume files were sent. Select at least one PDF and try again.';
    default:
      return status >= 500
        ? 'The screening service could not complete this batch. Your files are still selected, so you can try again.'
        : `Unexpected response from the server (HTTP ${status}).`;
  }
}

// Light structural check only. The backend is the authority on content.
export function parseScreeningResults(value: unknown): ScreeningResults {
  const v = value as Partial<ScreeningResults> | null;
  const ok =
    !!v &&
    typeof v === 'object' &&
    typeof v.batch_summary === 'object' &&
    v.batch_summary !== null &&
    typeof v.batch_summary.total_resumes === 'number' &&
    Array.isArray(v.eligible_candidates) &&
    Array.isArray(v.rejected_candidates) &&
    Array.isArray(v.failed_candidates) &&
    Array.isArray(v.duplicates);
  if (!ok) {
    throw new ApiError('invalid_response', 'The server returned results in an unexpected format.');
  }
  return v as ScreeningResults;
}

export function createApiClient(config: ClientConfig = {}): ApiClient {
  const baseUrl = (config.baseUrl ?? configuredBaseUrl()).replace(/\/+$/, '');
  const doFetch = config.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const screenTimeout = config.screenTimeoutMs ?? DEFAULT_SCREEN_TIMEOUT_MS;
  const quickTimeout = config.quickTimeoutMs ?? DEFAULT_QUICK_TIMEOUT_MS;

  async function request(
    path: string,
    init: RequestInit,
    timeoutMs: number,
    external?: AbortSignal,
  ): Promise<Response> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const onExternalAbort = () => controller.abort();
    external?.addEventListener('abort', onExternalAbort);
    try {
      return await doFetch(`${baseUrl}${path}`, { ...init, signal: controller.signal });
    } catch (err) {
      if (timedOut) {
        throw new ApiError('timeout', 'The request timed out before the server answered. Try again, or use a smaller batch.');
      }
      if (external?.aborted) throw new ApiError('aborted', 'Request cancelled.');
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError('aborted', 'Request cancelled.');
      }
      throw new ApiError(
        'offline',
        `Cannot reach the screening service at ${baseUrl}. Make sure the backend is running and that its CORS_ORIGINS allows this page.`,
      );
    } finally {
      clearTimeout(timer);
      external?.removeEventListener('abort', onExternalAbort);
    }
  }

  async function readJson(response: Response): Promise<unknown> {
    try {
      return await response.json();
    } catch {
      throw new ApiError('invalid_response', 'The server returned results in an unexpected format.');
    }
  }

  async function failFromResponse(response: Response): Promise<never> {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError('http', httpErrorMessage(response.status, detail), response.status);
  }

  return {
    baseUrl,

    async health() {
      const response = await request('/health', { method: 'GET' }, quickTimeout);
      if (!response.ok) await failFromResponse(response);
      const body = (await readJson(response)) as { status?: string };
      if (body.status !== 'ok') throw new ApiError('invalid_response', 'The service reported an unhealthy status.');
    },

    async results() {
      const response = await request('/results', { method: 'GET' }, quickTimeout * 2);
      if (response.status === 404) return null; // no completed run yet
      if (!response.ok) await failFromResponse(response);
      return parseScreeningResults(await readJson(response));
    },

    async screen(items, options, signal) {
      const form = new FormData();
      for (const item of items) form.append('files', item.file, item.name);
      const query = new URLSearchParams({
        use_llm: String(options.useLlm),
        use_github: String(options.useGithub),
      });
      const response = await request(`/screen?${query}`, { method: 'POST', body: form }, screenTimeout, signal);
      if (!response.ok) await failFromResponse(response);
      return parseScreeningResults(await readJson(response));
    },
  };
}

export const defaultApi: ApiClient = createApiClient();
