/**
 * Vite configuration for the frontend service: the React plugin, the port the service
 * listens on, and the proxy that forwards API calls to the backend.
 *
 * The frontend is its own service. The browser talks only to it; requests under the
 * API prefix are forwarded to the backend by the frontend's server, in development
 * (`vite`) and when serving the built bundle (`vite preview`) alike. The backend's
 * address is read from the same variables the backend reads (`TICKET_AGENT_HOST`,
 * `TICKET_AGENT_PORT`), from the process environment or the repository's `.env`, so
 * the two services agree without a second configuration.
 */

import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Prefix of the variables read from the environment and `.env`.
const ENVIRONMENT_PREFIX = "TICKET_AGENT_";

// Backend defaults, the same values the backend's `settings.py` falls back to.
const DEFAULT_BACKEND_HOST = "127.0.0.1";
const DEFAULT_BACKEND_PORT = "8000";

// Port this service listens on when `TICKET_AGENT_FRONTEND_PORT` is unset.
const DEFAULT_FRONTEND_PORT = 5173;

// Path prefix that the frontend's server forwards to the backend.
const API_PATH_PREFIX = "/api";

// The repository root holds the shared `.env` file, one level above this package.
const repositoryRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, repositoryRoot, ENVIRONMENT_PREFIX);
  const backendHost = environment.TICKET_AGENT_HOST ?? DEFAULT_BACKEND_HOST;
  const backendPort = environment.TICKET_AGENT_PORT ?? DEFAULT_BACKEND_PORT;
  const backendUrl = `http://${backendHost}:${backendPort}`;
  const configuredFrontendPort = environment.TICKET_AGENT_FRONTEND_PORT;
  const frontendPort =
    configuredFrontendPort === undefined
      ? DEFAULT_FRONTEND_PORT
      : Number.parseInt(configuredFrontendPort, 10);

  const apiProxy = {
    [API_PATH_PREFIX]: {
      target: backendUrl,
      changeOrigin: true,
    },
  };

  return {
    plugins: [react()],
    server: {
      port: frontendPort,
      strictPort: true,
      proxy: apiProxy,
    },
    preview: {
      port: frontendPort,
      strictPort: true,
      proxy: apiProxy,
    },
  };
});
