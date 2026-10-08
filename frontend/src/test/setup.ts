import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => cleanup());

// jsdom has no object URLs or layout
if (!('createObjectURL' in URL)) {
  Object.assign(URL, { createObjectURL: () => 'blob:mock', revokeObjectURL: () => undefined });
}
