import type { ReactNode } from 'react';
import { Inbox } from 'lucide-react';

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Inbox size={22} aria-hidden="true" />
      <p className="empty-title">{title}</p>
      {children && <p className="muted">{children}</p>}
    </div>
  );
}
