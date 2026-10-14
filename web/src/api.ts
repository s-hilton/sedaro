// Base path for the backend API. The Vite dev server forwards `/api/*` to the backend (see
// `vite.config.ts`), so the browser only ever talks to the page's own origin. That works on
// localhost, in GitHub Codespaces and behind any other host or port forwarding, with no CORS setup.
export const API_URL = '/api';
