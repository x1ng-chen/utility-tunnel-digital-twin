import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, host: '0.0.0.0' },
  build: {
    sourcemap: true,
    target: 'es2022',
    // The WebGL engine is lazy-loaded exclusively by /twin-3d. Its
    // controlled budget is higher than the normal business-screen chunk.
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/three/') || id.includes('\\node_modules\\three\\')) return 'three-engine';
        },
      },
    },
  },
});
