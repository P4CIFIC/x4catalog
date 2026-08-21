import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: process.env.VITE_BASE || '/static/',
  plugins: [react()],
  build: {
    outDir: process.env.VITE_OUTDIR || '../static',
    emptyOutDir: Boolean(process.env.VITE_OUTDIR),
    rollupOptions: {
      output: {
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
});
