/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import pkg from './package.json';

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  server: {
    host: true,
    port: 3000,
    strictPort: true,
    // bind-mounted sources on Docker Desktop do not always emit file events
    watch: { usePolling: true, interval: 300 },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
  },
});
