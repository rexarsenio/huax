const DEFAULT_BASE_URL = "http://localhost:8081";

export const appConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL,
  refreshSeconds: Number(import.meta.env.VITE_REFRESH_SECONDS ?? 180),
  enableMetrics: import.meta.env.VITE_ENABLE_METRICS === "true",
};
