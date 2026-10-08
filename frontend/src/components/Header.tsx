import { FileCheck2, RefreshCw } from 'lucide-react';

export type HealthState = 'checking' | 'connected' | 'unavailable';

const TEXT: Record<HealthState, string> = {
  checking: 'Checking backend…',
  connected: 'Backend connected',
  unavailable: 'Backend unavailable',
};

export function Header({
  health,
  baseUrl,
  onRetry,
}: {
  health: HealthState;
  baseUrl: string;
  onRetry: () => void;
}) {
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <FileCheck2 size={16} />
          </span>
          <span className="brand-name">Resume Screen</span>
          <span className="brand-sub">AI Resume Screening</span>
        </div>
        <div className="header-right">
          <span className={`health health-${health}`} role="status" title={baseUrl}>
            <span className="health-dot" aria-hidden="true" />
            {TEXT[health]}
          </span>
          {health === 'unavailable' && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
              <RefreshCw size={14} aria-hidden="true" />
              Retry
            </button>
          )}
          <span className="version mono">v{__APP_VERSION__}</span>
        </div>
      </div>
    </header>
  );
}
