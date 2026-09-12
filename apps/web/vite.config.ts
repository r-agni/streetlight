import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@sfcs/protocol': fileURLToPath(new URL('../../packages/protocol/src/index.ts', import.meta.url)),
    },
  },
  // MapLibre 6 ships an ES-module worker. Letting Vite pre-bundle the package
  // rewrites the worker URL to a path it never serves, which silently leaves the
  // map with a background and no vector layers at all.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  worker: { format: 'es' },
  server: {
    port: 5173,
    fs: { allow: ['..', '../..'] },
  },
});
