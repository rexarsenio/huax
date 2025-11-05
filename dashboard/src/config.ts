const DEFAULT_BASE_URL = "http://localhost:8000";

export const appConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL,
  refreshSeconds: Number(import.meta.env.VITE_REFRESH_SECONDS ?? 180),
  enableMetrics: import.meta.env.VITE_ENABLE_METRICS === "true",
  features: {
    overviewV16: import.meta.env.VITE_DASHBOARD_OVERVIEW_V16 === "true",
  },
  openSea: {
    gateId: import.meta.env.VITE_OPEN_SEA_GATE_ID ?? "GATE_GIBRALTAR_E_v1",
    gateWindow: (import.meta.env.VITE_OPEN_SEA_GATE_WINDOW ?? "d7").toLowerCase(),
    corridorId: import.meta.env.VITE_OPEN_SEA_CORRIDOR ?? "CHOKEPOINT_GIBRALTAR->UNK",
    sisWindow: (import.meta.env.VITE_OPEN_SEA_SIS_WINDOW ?? "d7").toLowerCase(),
  },
};
