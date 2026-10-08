import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from '../App';
import { ApiError } from '../api/client';
import type { ApiClient } from '../api/client';
import type { ScreeningResults } from '../types/results';
import { eligible, github, makeApi, pdf, results, score } from './fixtures';

const user = () => userEvent.setup({ applyAccept: false });

async function selectFiles(u: ReturnType<typeof user>, files: File[], testId = 'file-input') {
  await u.upload(screen.getByTestId(testId), files);
}

async function openResults(api: ApiClient = makeApi(), files = [pdf('a.pdf'), pdf('b.pdf')]) {
  const u = user();
  render(<App api={api} />);
  await screen.findByText('Backend connected');
  await selectFiles(u, files);
  await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
  await screen.findByRole('heading', { name: 'Resume Screening' });
  return u;
}

describe('upload screen', () => {
  it('renders the empty state with the backend status', async () => {
    render(<App api={makeApi()} />);
    expect(screen.getByRole('heading', { name: 'AI Resume Screening' })).toBeInTheDocument();
    expect(screen.getByText('Drop resume PDFs here')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Choose Files/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Choose Folder/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Process Resumes' })).toBeDisabled();
    expect(screen.getByText('Select at least one resume PDF to begin.')).toBeInTheDocument();
    expect(await screen.findByText('Backend connected')).toBeInTheDocument();
  });

  it('lists selected files and lets the user remove one or clear all', async () => {
    const u = user();
    render(<App api={makeApi()} />);
    await selectFiles(u, [pdf('alpha.pdf', 1500), pdf('beta.pdf', 3 * 1024 * 1024)]);
    expect(screen.getByText('2 resumes selected')).toBeInTheDocument();
    expect(screen.getByText('alpha.pdf')).toBeInTheDocument();
    expect(screen.getByText('3.0 MB')).toBeInTheDocument();

    await u.click(screen.getByRole('button', { name: 'Remove alpha.pdf' }));
    expect(screen.queryByText('alpha.pdf')).not.toBeInTheDocument();
    expect(screen.getByText('1 resume selected')).toBeInTheDocument();

    await u.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(screen.queryByText('beta.pdf')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Process Resumes' })).toBeDisabled();
  });

  it('skips unsupported and oversized files with a notice instead of failing', async () => {
    const u = user();
    render(<App api={makeApi()} />);
    await selectFiles(u, [pdf('ok.pdf'), pdf('notes.docx'), pdf('photo.png'), pdf('.DS_Store'), pdf('huge.pdf', 21 * 1024 * 1024)]);
    expect(screen.getByText('1 resume selected')).toBeInTheDocument();
    const notice = screen.getByText('Some files were not added').closest('.banner') as HTMLElement;
    expect(within(notice).getByText(/Skipped 2 unsupported files.*notes\.docx, photo\.png/)).toBeInTheDocument();
    expect(within(notice).getByText(/Skipped 1 file over 20 MB: huge\.pdf/)).toBeInTheDocument();
    expect(notice).not.toHaveTextContent('.DS_Store');
  });

  it('ignores files that were already selected', async () => {
    const u = user();
    render(<App api={makeApi()} />);
    const file = pdf('same.pdf');
    await selectFiles(u, [file]);
    await selectFiles(u, [file]);
    expect(screen.getByText('1 resume selected')).toBeInTheDocument();
    expect(screen.getByText(/already selected/)).toBeInTheDocument();
  });

  it('supports folder selection: keeps relative paths, skips non-PDFs, same batch endpoint', async () => {
    const api = makeApi();
    const u = user();
    render(<App api={api} />);
    expect(screen.getByTestId('folder-input')).toHaveAttribute('webkitdirectory');
    await selectFiles(u, [pdf('cv.pdf', 100, 'batch/team_a/cv.pdf'), pdf('cv.pdf', 200, 'batch/team_b/cv.pdf'), pdf('readme.txt', 10, 'batch/readme.txt')], 'folder-input');
    expect(screen.getByText('2 resumes selected')).toBeInTheDocument();
    await screen.findByText('Backend connected');
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
    await screen.findByRole('heading', { name: 'Resume Screening' });
    const items = (api.screen as ReturnType<typeof vi.fn>).mock.calls[0][0] as { name: string }[];
    expect(items.map((i) => i.name)).toEqual(['batch/team_a/cv.pdf', 'batch/team_b/cv.pdf']);
  });

  it('accepts dropped files', async () => {
    render(<App api={makeApi()} />);
    const zone = screen.getByTestId('dropzone');
    const dropped = pdf('dropped.pdf');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.dragEnter(zone);
    expect(screen.getByText('Release to add files')).toBeInTheDocument();
    fireEvent.drop(zone, { dataTransfer: { files: [dropped] } });
    expect(await screen.findByText('dropped.pdf')).toBeInTheDocument();
    expect(screen.getByText('Drop resume PDFs here')).toBeInTheDocument();
  });
});

describe('backend health', () => {
  it('shows an unavailable backend clearly and blocks processing', async () => {
    const u = user();
    const api = makeApi({ health: vi.fn().mockRejectedValue(new ApiError('offline', 'Cannot reach')) });
    render(<App api={api} />);
    expect(await screen.findByText('Backend unavailable', { selector: '.health' })).toBeInTheDocument();
    expect(screen.getByText('Backend unavailable', { selector: '.banner-title' })).toBeInTheDocument();
    await selectFiles(u, [pdf('a.pdf')]);
    expect(screen.getByRole('button', { name: 'Process Resumes' })).toBeDisabled();
    expect(screen.getByText(/backend is unavailable/i)).toBeInTheDocument();
  });

  it('recovers when Retry succeeds', async () => {
    const health = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue(undefined);
    render(<App api={makeApi({ health })} />);
    await screen.findByText('Backend unavailable', { selector: '.health' });
    await userEvent.click(screen.getAllByRole('button', { name: /Retry/ })[0]);
    expect(await screen.findByText('Backend connected')).toBeInTheDocument();
  });
});

describe('processing', () => {
  it('sends the files and options, shows an honest loading state, then the dashboard', async () => {
    let resolve!: (r: ScreeningResults) => void;
    const screenFn = vi.fn().mockReturnValue(new Promise<ScreeningResults>((r) => { resolve = r; }));
    const api = makeApi({ screen: screenFn });
    const u = user();
    render(<App api={api} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf'), pdf('b.pdf')]);
    await u.click(screen.getByText('Analysis options'));
    await u.click(screen.getByLabelText(/GitHub enrichment/));
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));

    expect(await screen.findByRole('heading', { name: 'Processing 2 resumes…' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Process Resumes' })).not.toBeInTheDocument(); // no double submit
    expect(screen.getByText(/does not report live progress/)).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument(); // no fake percentages
    expect(screenFn).toHaveBeenCalledTimes(1);
    expect(screenFn.mock.calls[0][1]).toEqual({ useLlm: true, useGithub: false });
    expect((screenFn.mock.calls[0][0] as unknown[]).length).toBe(2);

    resolve(results());
    expect(await screen.findByRole('heading', { name: 'Resume Screening' })).toBeInTheDocument();
  });

  it('keeps the selection and shows a safe, retryable error when processing fails', async () => {
    const screenFn = vi.fn()
      .mockRejectedValueOnce(new ApiError('http', 'The screening service could not complete this batch. Your files are still selected, so you can try again.', 500))
      .mockResolvedValueOnce(results());
    const u = user();
    render(<App api={makeApi({ screen: screenFn })} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf')]);
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Processing failed')).toBeInTheDocument();
    expect(alert).not.toHaveTextContent(/Traceback|undefined|Error:/);
    expect(screen.getByText('a.pdf')).toBeInTheDocument(); // not lost

    await u.click(within(alert).getByRole('button', { name: 'Try Again' }));
    expect(await screen.findByRole('heading', { name: 'Resume Screening' })).toBeInTheDocument();
    expect(screenFn).toHaveBeenCalledTimes(2);
  });

  it.each([
    [409, 'Another screening run is currently in progress. Please try again after it finishes.'],
    [413, 'This batch exceeds the server upload limits. Remove some files or reduce file sizes.'],
  ])('shows the actionable message for HTTP %i', async (status, message) => {
    const u = user();
    render(<App api={makeApi({ screen: vi.fn().mockRejectedValue(new ApiError('http', message, status)) })} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf')]);
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it('turns a network failure into the backend-unavailable state (one banner, files kept)', async () => {
    const u = user();
    const screenFn = vi.fn().mockRejectedValue(new ApiError('offline', 'Cannot reach the screening service at http://api.test.'));
    render(<App api={makeApi({ screen: screenFn })} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf')]);
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
    expect(await screen.findByText('Backend unavailable', { selector: '.health' })).toBeInTheDocument();
    expect(screen.getByText('Backend unavailable', { selector: '.banner-title' })).toBeInTheDocument();
    expect(screen.queryByText('Processing failed')).not.toBeInTheDocument();
    expect(screen.getByText('a.pdf')).toBeInTheDocument();
  });

  it('hides unexpected error internals behind a generic message', async () => {
    const u = user();
    render(<App api={makeApi({ screen: vi.fn().mockRejectedValue(new Error('boom: internals at /srv/app.py')) })} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf')]);
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Something went wrong while processing. Please try again.');
    expect(alert).not.toHaveTextContent(/boom|internals|\/srv/);
  });

  it('lets the user stop waiting without losing the selection', async () => {
    const screenFn = vi.fn().mockImplementation((_f, _o, signal: AbortSignal) =>
      new Promise((_res, rej) => signal.addEventListener('abort', () => rej(new ApiError('aborted', 'Request cancelled.')))));
    const u = user();
    render(<App api={makeApi({ screen: screenFn })} />);
    await screen.findByText('Backend connected');
    await selectFiles(u, [pdf('a.pdf')]);
    await u.click(screen.getByRole('button', { name: 'Process Resumes' }));
    await u.click(await screen.findByRole('button', { name: 'Stop waiting' }));
    expect(await screen.findByText('Stopped waiting')).toBeInTheDocument();
    expect(screen.getByText('a.pdf')).toBeInTheDocument();
  });
});

describe('results dashboard', () => {
  it('shows the backend batch summary exactly, keeping failed, rejected and duplicates apart', async () => {
    await openResults();
    const stat = (label: string) => screen.getByText(label, { selector: '.stat-label' }).closest('.stat') as HTMLElement;
    expect(within(stat('Total resumes')).getByText('9')).toBeInTheDocument();
    expect(within(stat('Successfully parsed')).getByText('5')).toBeInTheDocument();
    expect(within(stat('Eligible')).getByText('2')).toBeInTheDocument();
    expect(within(stat('Rejected')).getByText('3')).toBeInTheDocument();
    expect(within(stat('Failed')).getByText('2')).toBeInTheDocument();
    expect(within(stat('Duplicates')).getByText('2')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Batch outcome: Eligible 2, Rejected 3, Failed 2, Duplicates 2' })).toBeInTheDocument();
    expect(screen.getByText('9 resumes processed', { exact: false })).toBeInTheDocument();
  });

  it('renders eligible candidates in the backend order, never re-sorted', async () => {
    const odd = results({
      eligible_candidates: [eligible('Low Scorer', 1, 50), eligible('High Scorer', 2, 90), eligible('Mid Scorer', 3, 70)],
    });
    await openResults(makeApi({ screen: vi.fn().mockResolvedValue(odd) }));
    const names = within(screen.getByRole('list', { name: 'Ranked eligible candidates' })).getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(names).toEqual(['Low Scorer', 'High Scorer', 'Mid Scorer']);
    expect(screen.getByText('#1')).toBeInTheDocument();
  });

  it('shows rank, score, per-category scores against backend maxima, summary, skills, strengths', async () => {
    await openResults();
    const card = screen.getByRole('button', { name: 'Open details for Jane Doe' });
    expect(within(card).getByText('#1')).toBeInTheDocument();
    expect(within(card).getByText('91')).toBeInTheDocument();
    expect(within(card).getByRole('meter', { name: 'AI / Agentic / RAG: 36 of 40' })).toBeInTheDocument();
    expect(within(card).getByRole('meter', { name: 'GitHub: 10 of 10' })).toBeInTheDocument();
    expect(within(card).getByText('Research Assistant Agent')).toBeInTheDocument();
    expect(within(card).getByText('LangGraph')).toBeInTheDocument();
    expect(within(card).getByText(/AI depth in Research Assistant Agent/)).toBeInTheDocument();
  });

  it('shows rejection reasons exactly as supplied by the backend', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /Rejected/ }));
    const list = screen.getByRole('list', { name: 'Rejected candidates' });
    expect(within(list).getByText('Asha Rao')).toBeInTheDocument();
    expect(within(list).getByText('No Python evidence found: Python in skills, a project, or work/internship experience.')).toBeInTheDocument();
    expect(within(list).getByText('No AI/LLM/RAG/agentic evidence found.')).toBeInTheDocument();
    expect(within(list).getAllByText('Not eligible')).toHaveLength(3);
    expect(screen.queryByRole('list', { name: 'Ranked eligible candidates' })).not.toBeInTheDocument();
  });

  it('lists processing failures separately and says failed is not rejected', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /Failed/ }));
    const list = screen.getByRole('list', { name: 'Processing failures' });
    expect(within(list).getByText('corrupt.pdf')).toBeInTheDocument();
    expect(within(list).getByText('UnsupportedFormatError')).toBeInTheDocument();
    expect(within(list).getByText('Unsupported file type')).toBeInTheDocument();
    expect(screen.getByText(/Failed is not rejected/)).toBeInTheDocument();
  });

  it('shows duplicates, expandable, without hashes', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /Duplicates/ }));
    expect(screen.getByText('2 files skipped')).toBeInTheDocument();
    expect(screen.getByText('jane_copy.pdf')).toBeVisible();
    expect(screen.getByText('jane_doe.pdf')).toBeInTheDocument();
    expect(screen.getByText('identical text')).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('hash-');
  });

  it('filters by search (name, skill, filename) and by tab without changing order', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /^All/ }));
    const search = screen.getByRole('searchbox');
    await u.type(search, 'django');
    expect(screen.getByRole('button', { name: 'Open details for Sam Lee' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open details for Jane Doe' })).not.toBeInTheDocument();
    expect(screen.queryByText('Processing failures')).not.toBeInTheDocument();

    await u.clear(search);
    await u.type(search, 'corrupt');
    expect(screen.getByText('corrupt.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open details for Sam Lee' })).not.toBeInTheDocument();

    await u.clear(search);
    await u.type(search, 'zzz-no-match');
    expect(screen.getByText('No results match “zzz-no-match”')).toBeInTheDocument();
  });

  it('shows an empty-eligible message when nothing was eligible', async () => {
    const none = results({
      batch_summary: { ...results().batch_summary, eligible: 0, total_resumes: 6, successfully_parsed: 3, failed: 1, duplicates: 2 },
      eligible_candidates: [],
    });
    await openResults(makeApi({ screen: vi.fn().mockResolvedValue(none) }));
    expect(screen.getByText('No eligible candidates')).toBeInTheDocument();
  });

  it('returns to a clean upload screen for another batch', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /Process another batch/ }));
    expect(screen.getByRole('heading', { name: 'AI Resume Screening' })).toBeInTheDocument();
    expect(screen.queryByText('a.pdf')).not.toBeInTheDocument();
  });
});

describe('candidate details', () => {
  async function openJane(over?: ScreeningResults) {
    const u = await openResults(makeApi({ screen: vi.fn().mockResolvedValue(over ?? results()) }));
    await u.click(screen.getByRole('button', { name: 'Open details for Jane Doe' }));
    return { u, dialog: await screen.findByRole('dialog', { name: 'Jane Doe' }) };
  }

  it('shows identity, total, the five categories and strengths/concerns/skills/projects', async () => {
    const { dialog } = await openJane();
    expect(within(dialog).getByText('jane_doe@example.com')).toBeInTheDocument();
    expect(within(dialog).getByText('jane_doe.pdf')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Total score 91 out of 100')).toBeInTheDocument();
    for (const [label, pts, max] of [['AI / Agentic / RAG', 36, 40], ['Python & Backend', 27, 30], ['Cloud / Full Stack', 13, 15], ['GitHub', 10, 10], ['Engineering Depth', 5, 5]] as const) {
      expect(within(dialog).getByRole('meter', { name: `${label}: ${pts} of ${max}` })).toBeInTheDocument();
    }
    expect(within(dialog).getByText('Strengths')).toBeInTheDocument();
    expect(within(dialog).getByText('Concerns')).toBeInTheDocument();
    expect(within(dialog).getByText('Matched skills')).toBeInTheDocument();
    expect(within(dialog).getByText('Built a stateful agentic workflow with retrieval and tool calling')).toBeInTheDocument();
  });

  it('shows penalties separately with the backend reason', async () => {
    const penalised = results({
      eligible_candidates: [eligible('Jane Doe', 1, 40, {
        score_breakdown: score({
          total_score: 40,
          penalties: [{ code: 'shallow_ai_project', amount: 15, reason: 'AI work looks like a thin LLM/API wrapper: no retrieval or tools found', evidence: [] }],
        }),
      })],
    });
    const { dialog } = await openJane(penalised);
    expect(within(dialog).getByText('Project-quality penalty', { selector: 'strong' })).toBeInTheDocument();
    expect(within(dialog).getByText('−15', { selector: '.penalty-amount' })).toBeInTheDocument();
    expect(within(dialog).getByText(/thin LLM\/API wrapper/)).toBeInTheDocument();
  });

  it('shows GitHub details when enrichment succeeded', async () => {
    const { dialog } = await openJane();
    const gh = within(dialog).getByRole('region', { name: 'GitHub' });
    expect(within(gh).getByText('10')).toBeInTheDocument();
    expect(gh).toHaveTextContent('recent activity 5/5');
    expect(gh).toHaveTextContent('repositories 5/5');
    const repo = within(gh).getByRole('link', { name: 'rag-service' });
    expect(repo).toHaveAttribute('href', 'https://github.com/janedoe/rag-service');
    expect(repo).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it.each([
    ['missing', 'Not available: no GitHub link on the resume'],
    ['rate_limited', 'Unavailable: GitHub API rate limited'],
    ['not_found', 'Unavailable: GitHub profile not found'],
    ['timeout', 'Unavailable: GitHub API timed out'],
  ] as const)('shows GitHub %s as unavailable, not as a rejection', async (status, text) => {
    const c = eligible('Jane Doe', 1, 70, {
      github_url: null,
      github_enrichment: github({ status, total_points: 0, recent_activity_points: 0, repository_points: 0, summary: null, evidence: [], relevant_repositories: [], profile_url: null }),
      score_breakdown: score({ github: 0, github_status: status, total_score: 70 }),
    });
    const { dialog } = await openJane(results({ eligible_candidates: [c] }));
    const gh = within(dialog).getByRole('region', { name: 'GitHub' });
    expect(within(gh).getByText(text)).toBeInTheDocument();
    expect(gh).toHaveTextContent('does not affect eligibility');
    expect(within(dialog).getByText('Eligible · rank #1')).toBeInTheDocument();
  });

  it('closes with Escape and restores focus to the opener', async () => {
    const { u } = await openJane();
    await u.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open details for Jane Doe' })).toHaveFocus();
  });

  it('closes with the close button and the backdrop', async () => {
    const { u, dialog } = await openJane();
    await u.click(within(dialog).getByRole('button', { name: 'Close details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Open details for Jane Doe' }));
    await screen.findByRole('dialog');
    await u.click(document.querySelector('.drawer-backdrop') as HTMLElement);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the exact candidate JSON on demand and copies it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const { u, dialog } = await openJane();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    expect(within(dialog).queryByLabelText('Candidate JSON')).toHaveTextContent(''); // not rendered until opened
    await u.click(within(dialog).getByText('View JSON'));
    const pre = within(dialog).getByLabelText('Candidate JSON');
    expect(JSON.parse(pre.textContent ?? '')).toEqual(results().eligible_candidates[0]);
    await u.click(within(dialog).getByRole('button', { name: /Copy JSON/ }));
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(results().eligible_candidates[0], null, 2));
    expect(await within(dialog).findByText('Copied')).toBeInTheDocument();
  });

  it('opens a rejected candidate with reasons and what was found', async () => {
    const u = await openResults();
    await u.click(screen.getByRole('button', { name: /Rejected/ }));
    await u.click(screen.getByRole('button', { name: 'Open details for Asha Rao' }));
    const dialog = await screen.findByRole('dialog', { name: 'Asha Rao' });
    expect(within(dialog).getByText('Why this candidate is not eligible')).toBeInTheDocument();
    expect(within(dialog).getAllByText(/No Python evidence found/).length).toBeGreaterThan(0);
    expect(within(dialog).queryByLabelText(/Total score/)).not.toBeInTheDocument(); // no invented score
    await u.click(within(dialog).getByText(/What was found in the resume/));
    expect(within(dialog).getByText('Built a RAG pipeline in Java')).toBeInTheDocument();
  });
});

describe('download and latest results', () => {
  it('downloads the complete backend JSON unmodified', async () => {
    const data = results();
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('resume-screening-results.json');
    });
    const u = await openResults(makeApi({ screen: vi.fn().mockResolvedValue(data) }));
    await u.click(screen.getByRole('button', { name: /Download JSON/ }));

    expect(click).toHaveBeenCalledTimes(1);
    const blob = create.mock.calls[0][0] as Blob;
    expect(blob.type).toBe('application/json');
    const text = await new Promise<string>((res) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.readAsText(blob); });
    expect(text).toBe(JSON.stringify(data, null, 2));
    expect(JSON.parse(text)).toEqual(data);
  });

  it('offers the previous results from /results without forcing them', async () => {
    const api = makeApi({ results: vi.fn().mockResolvedValue(results()) });
    const u = user();
    render(<App api={api} />);
    expect(await screen.findByText('Previous screening results available')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'AI Resume Screening' })).toBeInTheDocument(); // still the upload screen
    expect(screen.getByText(/2 eligible of 9 resumes/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'View latest results' }));
    expect(await screen.findByRole('heading', { name: 'Resume Screening' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open details for Jane Doe' })).toBeInTheDocument();
  });

  it('shows no previous-results banner when the backend has none', async () => {
    render(<App api={makeApi()} />);
    await screen.findByText('Backend connected');
    await waitFor(() => expect(screen.queryByText('Previous screening results available')).not.toBeInTheDocument());
  });

  it('never persists candidate data in browser storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    await openResults();
    expect(setItem).not.toHaveBeenCalled();
  });
});
