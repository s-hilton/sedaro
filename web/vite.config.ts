import viteReact from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import viteSvgr from 'vite-plugin-svgr';
import viteTsconfigPaths from 'vite-tsconfig-paths';

// https://vitejs.dev/config/
export default defineConfig({
  base: '/',
  plugins: [viteReact(), viteTsconfigPaths(), viteSvgr()],
  server: {
    host: true,
    port: 3030,
    // The frontend calls the API at `/api/*` on its own origin and this dev server forwards it to the
    // backend, so the browser never makes a cross-origin request. Docker Compose sets API_URL to
    // reach the backend through the Docker host; otherwise it is on this machine.
    proxy: {
      '/api': {
        target: process.env.API_URL ?? 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
