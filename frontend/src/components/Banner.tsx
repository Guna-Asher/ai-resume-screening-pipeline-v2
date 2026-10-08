import type { ReactNode } from 'react';
import { AlertTriangle, Info, XCircle } from 'lucide-react';

type BannerTone = 'info' | 'warn' | 'error';

const ICONS = { info: Info, warn: AlertTriangle, error: XCircle };

export function Banner({
  tone,
  title,
  children,
  actions,
}: {
  tone: BannerTone;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div className={`banner banner-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" className="banner-icon" />
      <div className="banner-body">
        <p className="banner-title">{title}</p>
        {children && <div className="banner-text">{children}</div>}
      </div>
      {actions && <div className="banner-actions">{actions}</div>}
    </div>
  );
}
