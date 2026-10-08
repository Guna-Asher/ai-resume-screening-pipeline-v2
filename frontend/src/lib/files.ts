// Lightweight selection validation only. The backend remains authoritative about content.
import type { UploadItem } from '../api/client';

export const ACCEPTED_EXTENSIONS = ['.pdf'];
export const MAX_FILE_BYTES = 20 * 1024 * 1024; // matches the backend's documented per-file limit

export interface SelectedFile extends UploadItem {
  id: string;
}

export interface AddResult {
  accepted: SelectedFile[];
  notices: string[];
}

function relativeName(file: File): string {
  const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
  return path && path.length > 0 ? path : file.name;
}

function key(file: File): string {
  return `${relativeName(file)}|${file.size}|${file.lastModified}`;
}

function listNames(names: string[]): string {
  const shown = names.slice(0, 3).join(', ');
  return names.length > 3 ? `${shown} and ${names.length - 3} more` : shown;
}

export function addFiles(existing: SelectedFile[], incoming: File[]): AddResult {
  const seen = new Set(existing.map((s) => key(s.file)));
  const accepted: SelectedFile[] = [];
  const unsupported: string[] = [];
  const oversized: string[] = [];
  let repeats = 0;

  for (const file of incoming) {
    const name = relativeName(file);
    const lower = name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      // hidden files such as .DS_Store are noise in folder picks; do not nag about them
      if (!name.split('/').pop()?.startsWith('.')) unsupported.push(name);
      continue;
    }
    if (file.size > MAX_FILE_BYTES) {
      oversized.push(name);
      continue;
    }
    if (seen.has(key(file))) {
      repeats += 1;
      continue;
    }
    seen.add(key(file));
    accepted.push({ id: `${key(file)}#${accepted.length}-${existing.length}`, file, name });
  }

  const notices: string[] = [];
  if (unsupported.length) {
    notices.push(`Skipped ${unsupported.length} unsupported file${unsupported.length === 1 ? '' : 's'} (only PDF resumes are supported): ${listNames(unsupported)}`);
  }
  if (oversized.length) {
    notices.push(`Skipped ${oversized.length} file${oversized.length === 1 ? '' : 's'} over 20 MB: ${listNames(oversized)}`);
  }
  if (repeats) {
    notices.push(`${repeats} file${repeats === 1 ? ' was' : 's were'} already selected and ${repeats === 1 ? 'was' : 'were'} ignored.`);
  }
  return { accepted, notices };
}
