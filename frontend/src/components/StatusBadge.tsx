import type { ReactNode } from 'react';

export type Tone = 'good' | 'bad' | 'warn' | 'neutral' | 'accent';

export function StatusBadge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}
