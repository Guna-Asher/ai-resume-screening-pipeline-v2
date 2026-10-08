import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { FileText, FolderOpen, UploadCloud, X } from 'lucide-react';
import type { ScreenOptions } from '../api/client';
import type { SelectedFile } from '../lib/files';
import { formatBytes, pluralize } from '../lib/format';
import { Banner } from './Banner';

interface Props {
  files: SelectedFile[];
  notices: string[];
  options: ScreenOptions;
  disabledReason: string | null;
  onAddFiles: (files: File[]) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
  onDismissNotices: () => void;
  onOptionsChange: (options: ScreenOptions) => void;
  onProcess: () => void;
}

export function UploadPanel({
  files, notices, options, disabledReason,
  onAddFiles, onRemove, onClear, onDismissNotices, onOptionsChange, onProcess,
}: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  const totalBytes = files.reduce((n, f) => n + f.file.size, 0);

  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = ''; // allow choosing the same files again after removing them
    if (picked.length) onAddFiles(picked);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    const dropped = Array.from(event.dataTransfer.files);
    if (dropped.length) onAddFiles(dropped);
  };

  return (
    <section className="card upload" aria-labelledby="upload-title">
      <div className="upload-head">
        <h1 id="upload-title">AI Resume Screening</h1>
        <p className="muted">
          Upload a batch of candidate resumes to evaluate Python + AI/agentic eligibility, engineering depth,
          cloud exposure and public GitHub activity.
        </p>
      </div>

      <div
        className={`dropzone ${dragging ? 'is-dragging' : ''}`}
        data-testid="dropzone"
        onDragEnter={(e) => { e.preventDefault(); dragDepth.current += 1; setDragging(true); }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => { dragDepth.current = Math.max(0, dragDepth.current - 1); if (dragDepth.current === 0) setDragging(false); }}
        onDrop={onDrop}
      >
        <UploadCloud size={30} aria-hidden="true" className="dropzone-icon" />
        <p className="dropzone-title">{dragging ? 'Release to add files' : 'Drop resume PDFs here'}</p>
        <p className="muted">or choose files / choose a folder</p>
        <div className="dropzone-actions">
          <button type="button" className="btn btn-primary" onClick={() => fileInput.current?.click()}>
            <FileText size={16} aria-hidden="true" /> Choose Files
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => folderInput.current?.click()}>
            <FolderOpen size={16} aria-hidden="true" /> Choose Folder
          </button>
        </div>
        <p className="dropzone-foot">PDF resumes · batch supported · dropping a folder is not reliable in every browser, so use “Choose Folder”</p>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,application/pdf"
          hidden
          aria-label="Choose resume PDF files"
          data-testid="file-input"
          onChange={pick}
        />
        <input
          ref={folderInput}
          type="file"
          multiple
          hidden
          aria-label="Choose a folder of resumes"
          data-testid="folder-input"
          {...({ webkitdirectory: '' } as Record<string, string>)}
          onChange={pick}
        />
      </div>

      {notices.length > 0 && (
        <Banner
          tone="warn"
          title="Some files were not added"
          actions={<button type="button" className="btn btn-ghost btn-sm" onClick={onDismissNotices}>Dismiss</button>}
        >
          <ul className="notice-list">
            {notices.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </Banner>
      )}

      {files.length > 0 && (
        <div className="selected">
          <div className="selected-head">
            <p className="selected-count">
              <strong>{pluralize(files.length, 'resume')} selected</strong>
              <span className="muted"> · {formatBytes(totalBytes)}</span>
            </p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>Clear all</button>
          </div>
          <ul className="file-list" aria-label="Selected resumes">
            {files.map((f) => (
              <li key={f.id} className="file-row">
                <FileText size={16} aria-hidden="true" className="muted" />
                <span className="file-name mono truncate" title={f.name}>{f.name}</span>
                <span className="badge badge-neutral">PDF</span>
                <span className="file-size muted">{formatBytes(f.file.size)}</span>
                <button type="button" className="icon-btn" aria-label={`Remove ${f.name}`} onClick={() => onRemove(f.id)}>
                  <X size={15} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="options">
        <summary>Analysis options</summary>
        <label className="check">
          <input type="checkbox" checked={options.useLlm} onChange={(e) => onOptionsChange({ ...options, useLlm: e.target.checked })} />
          <span>
            LLM semantic analysis
            <small className="muted">Adds evidence when an LLM is configured on the server. Never decides eligibility or score.</small>
          </span>
        </label>
        <label className="check">
          <input type="checkbox" checked={options.useGithub} onChange={(e) => onOptionsChange({ ...options, useGithub: e.target.checked })} />
          <span>
            GitHub enrichment
            <small className="muted">Public activity and repositories, worth at most 10 points.</small>
          </span>
        </label>
      </details>

      <div className="cta">
        <button type="button" className="btn btn-primary btn-lg" disabled={disabledReason !== null} onClick={onProcess}>
          Process Resumes
        </button>
        {disabledReason && <p className="hint muted">{disabledReason}</p>}
      </div>
    </section>
  );
}
