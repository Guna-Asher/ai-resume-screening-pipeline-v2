import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../api/client';
import { pdf, results } from './fixtures';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function client(fetchImpl: typeof fetch, extra = {}) {
  return createApiClient({ baseUrl: 'http://api.test/', fetchImpl, ...extra });
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try { await promise; } catch (e) { return e as ApiError; }
  throw new Error('expected the call to fail');
}

describe('API client', () => {
  it('trims the base URL and checks /health', async () => {
    const f = vi.fn().mockResolvedValue(json({ status: 'ok' }));
    const c = client(f);
    await c.health();
    expect(c.baseUrl).toBe('http://api.test');
    expect(f.mock.calls[0][0]).toBe('http://api.test/health');
  });

  it('reports an unreachable backend as offline without leaking raw errors', async () => {
    const e = await failure(client(vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))).health());
    expect(e.kind).toBe('offline');
    expect(e.message).toContain('Cannot reach the screening service');
    expect(e.message).not.toContain('Failed to fetch');
  });

  it('sends every file as a multipart "files" field with the chosen options', async () => {
    const f = vi.fn().mockResolvedValue(json(results()));
    const files = [
      { file: pdf('a.pdf'), name: 'a.pdf' },
      { file: pdf('b.pdf'), name: 'team/b.pdf' }, // folder-relative name
    ];
    await client(f).screen(files, { useLlm: false, useGithub: true });
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/screen?use_llm=false&use_github=true');
    expect(init.method).toBe('POST');
    const form = init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    const sent = form.getAll('files') as File[];
    expect(sent.map((x) => x.name)).toEqual(['a.pdf', 'team/b.pdf']);
    expect(new Headers(init.headers).has('content-type')).toBe(false); // the browser sets the boundary
  });

  it('returns the backend response untouched', async () => {
    const data = results();
    const out = await client(vi.fn().mockResolvedValue(json(data))).screen([], { useLlm: true, useGithub: true });
    expect(out).toEqual(data);
  });

  it('treats 404 from /results as "no results yet"', async () => {
    expect(await client(vi.fn().mockResolvedValue(json({ detail: 'No results yet.' }, 404))).results()).toBeNull();
  });

  it.each([
    [400, { detail: 'No resume files found: only hidden files were uploaded.' }, 'only hidden files were uploaded'],
    [409, { detail: 'busy' }, 'Another screening run is currently in progress'],
    [413, { detail: 'too big' }, 'exceeds the server upload limits'],
    [422, { detail: [{ loc: ['body', 'files'], msg: 'Field required' }] }, 'no valid resume files were sent'],
    [500, { detail: 'Traceback (most recent call last): secret' }, 'could not complete this batch'],
    [503, 'upstream down', 'could not complete this batch'],
    [418, { detail: 'teapot' }, 'Unexpected response from the server (HTTP 418)'],
  ])('maps HTTP %i to a safe message', async (status, body, expected) => {
    const response = typeof body === 'string' ? new Response(body, { status }) : json(body, status as number);
    const e = await failure(client(vi.fn().mockResolvedValue(response)).screen([], { useLlm: true, useGithub: true }));
    expect(e.kind).toBe('http');
    expect(e.status).toBe(status);
    expect(e.message).toContain(expected);
    expect(e.message).not.toMatch(/Traceback|secret|teapot/);
  });

  it('rejects malformed or unexpected JSON as invalid_response', async () => {
    for (const response of [new Response('<html>oops</html>', { status: 200 }), json({ hello: 'world' }), json(null)]) {
      const e = await failure(client(vi.fn().mockResolvedValue(response)).screen([], { useLlm: true, useGithub: true }));
      expect(e.kind).toBe('invalid_response');
    }
    expect((await failure(client(vi.fn().mockResolvedValue(json({ nope: 1 }))).results())).kind).toBe('invalid_response');
  });

  it('times out slow requests', async () => {
    const hang = (_url: unknown, init?: RequestInit) =>
      new Promise<Response>((_res, rej) => init?.signal?.addEventListener('abort', () => rej(new DOMException('x', 'AbortError'))));
    const e = await failure(client(hang as typeof fetch, { screenTimeoutMs: 20 }).screen([], { useLlm: true, useGithub: true }));
    expect(e.kind).toBe('timeout');
  });

  it('distinguishes a user cancel from a timeout', async () => {
    const hang = (_url: unknown, init?: RequestInit) =>
      new Promise<Response>((_res, rej) => init?.signal?.addEventListener('abort', () => rej(new DOMException('x', 'AbortError'))));
    const controller = new AbortController();
    const pending = failure(client(hang as typeof fetch).screen([], { useLlm: true, useGithub: true }, controller.signal));
    controller.abort();
    expect((await pending).kind).toBe('aborted');
  });
});
