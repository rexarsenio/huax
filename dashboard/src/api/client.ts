import axios from "axios";
import { appConfig } from "../config";
import type {
  BasinIndexResponse,
  ComponentsResponse,
  GlobalIndexResponse,
  HealthStatus,
  OpsHealth,
  SignalsSnapshot,
  SpreadSignalsResponse,
  ThroughputNowcastResponse,
  RunMeta,
  IndexMeta,
  LatestIndexSnapshot,
  ChokepointSummaryResponse,
} from "./types";

const api = axios.create({
  baseURL: appConfig.apiBaseUrl,
  timeout: 30_000,
});

export const fetchGlobalIndex = async (range = "90d"): Promise<GlobalIndexResponse> => {
  const { data } = await api.get<GlobalIndexResponse>("/api/index/v1_5", { params: { range } });
  return data;
};

export const fetchBasinIndex = async (basin: string, range = "90d"): Promise<BasinIndexResponse> => {
  const { data } = await api.get<BasinIndexResponse>(`/api/index/${basin}`, { params: { range } });
  return data;
};

export const fetchBasinComponents = async (basin: string, range = "7d"): Promise<ComponentsResponse> => {
  const { data } = await api.get<ComponentsResponse>(`/api/components/${basin}`, { params: { range } });
  return data;
};

export const downloadBasinCsv = async (basin: string, range = "90d"): Promise<Blob> => {
  const { data } = await api.get(`/download/${basin}.csv`, {
    params: { range },
    responseType: "blob",
  });
  return data;
};

export const fetchSpreadSignals = async (): Promise<SpreadSignalsResponse> => {
  const { data } = await api.get<SpreadSignalsResponse>("/spread-signals", { params: { days: 90 } });
  return data;
};

export const fetchThroughputNowcast = async (): Promise<ThroughputNowcastResponse> => {
  const { data } = await api.get<ThroughputNowcastResponse>("/throughput-nowcast", { params: { days: 90 } });
  return data;
};

export const fetchLatestIndex = async (scope = "global"): Promise<LatestIndexSnapshot> => {
  const { data } = await api.get<LatestIndexSnapshot>("/api/index/latest", { params: { scope } });
  return data;
};

export const fetchChokepointSummary = async (window = "h24", gate?: string): Promise<ChokepointSummaryResponse> => {
  const params: Record<string, string> = { window };
  if (gate && gate !== "ALL") {
    params.gate = gate;
  }
  const { data } = await api.get<ChokepointSummaryResponse>("/api/open_sea/summary", { params });
  return data;
};

export const fetchSignalsSnapshot = async (): Promise<SignalsSnapshot> => {
  const { data } = await api.get<SignalsSnapshot>("/signals-snapshot");
  return data;
};

export const fetchHealth = async (): Promise<HealthStatus> => {
  try {
    const { data } = await api.get("/ready");
    return data;
  } catch {
    const fallback = await api.get("/health");
    return fallback.data;
  }
};

export const fetchOpsHealth = async (): Promise<OpsHealth> => {
  const { data } = await api.get<OpsHealth>("/ops/health");
  return data;
};

export const fetchRunMeta = async (): Promise<RunMeta> => {
  const { data } = await api.get<RunMeta>("/run_meta.json", { baseURL: undefined });
  return data;
};

export const fetchMetrics = async (): Promise<string> => {
  const { data } = await api.get<string>("/metrics", {
    responseType: "text",
    headers: { Accept: "text/plain" },
  });
  return data;
};

export const fetchMeta = async (): Promise<IndexMeta> => {
  const { data } = await api.get<IndexMeta>("/meta");
  return data;
};
