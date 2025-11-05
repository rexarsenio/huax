import { useQuery } from "@tanstack/react-query";
import {
  fetchHealth,
  fetchGlobalIndex,
  fetchBasinIndex,
  fetchBasinComponents,
  fetchOpsHealth,
  fetchMeta,
  fetchMetrics,
  fetchRunMeta,
  fetchSignalsSnapshot,
  fetchSpreadSignals,
  fetchThroughputNowcast,
  fetchLatestIndex,
  fetchChokepointSummary,
} from "../api/client";
import { fetchOil } from "../api/market";
import type { Basin } from "../api/types";
import { appConfig } from "../config";
import {
  fetchGateFlux,
  fetchSIS,
  fetchTransit,
  fetchCorridors,
  fetchSeaStateSummary,
  type GateFluxWindow,
  type TransitParams,
} from "../api/openSea";

export const useLatestIndex = (scope = "global", enabled = true) =>
  useQuery({
    queryKey: ["latest-index", scope],
    queryFn: () => fetchLatestIndex(scope),
    enabled,
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useGlobalIndex = (range = "90d") =>
  useQuery({
    queryKey: ["global-index", range],
    queryFn: () => fetchGlobalIndex(range),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useBasinIndex = (basin: Basin, range = "90d") =>
  useQuery({
    queryKey: ["basin-index", basin, range],
    queryFn: () => fetchBasinIndex(basin, range),
    enabled: basin !== "GLOBAL",
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useBasinComponents = (basin: Basin, range = "7d") =>
  useQuery({
    queryKey: ["basin-components", basin, range],
    queryFn: () => fetchBasinComponents(basin, range),
    enabled: basin !== "GLOBAL",
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useSpreadSignals = () =>
  useQuery({
    queryKey: ["spread-signals"],
    queryFn: fetchSpreadSignals,
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useThroughputNowcast = () =>
  useQuery({
    queryKey: ["throughput-nowcast"],
    queryFn: fetchThroughputNowcast,
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useSignalsSnapshot = () =>
  useQuery({
    queryKey: ["signals-snapshot"],
    queryFn: fetchSignalsSnapshot,
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useHealthStatus = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

export const useOpsHealth = () =>
  useQuery({
    queryKey: ["ops-health"],
    queryFn: fetchOpsHealth,
    refetchInterval: 30_000,
  });

export const useRunMeta = () =>
  useQuery({
    queryKey: ["run-meta"],
    queryFn: fetchRunMeta,
    refetchInterval: 5 * 60_000,
  });

export const useMetrics = () =>
  useQuery({
    queryKey: ["metrics"],
    queryFn: fetchMetrics,
    enabled: appConfig.enableMetrics,
    refetchInterval: appConfig.enableMetrics ? 60_000 : false,
  });

export const useIndexMeta = () =>
  useQuery({
    queryKey: ["index-meta"],
    queryFn: fetchMeta,
    staleTime: 30 * 60_000,
  });

const resolveGateWindow = (window: string | undefined): GateFluxWindow =>
  window === "d7" ? "d7" : "h24";

export const useGateFlux = (
  gateId: string,
  window: GateFluxWindow | string = appConfig.openSea.gateWindow,
  direction?: "AtoB" | "BtoA",
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: ["open-sea", "gate-flux", gateId, window, direction],
    queryFn: () => fetchGateFlux(gateId, resolveGateWindow(window), direction),
    enabled: Boolean(gateId) && (options?.enabled ?? true),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useSIS = (corridor: string, window = appConfig.openSea.sisWindow) =>
  useQuery({
    queryKey: ["open-sea", "sis", corridor, window],
    queryFn: () => fetchSIS(corridor, window),
    enabled: Boolean(corridor),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useOpenSeaSummary = (window = "h24", gate?: string) =>
  useQuery({
    queryKey: ["open-sea", "summary", window, gate ?? "ALL"],
    queryFn: () => fetchChokepointSummary(window, gate),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useTransit = (params?: TransitParams) =>
  useQuery({
    queryKey: [
      "open-sea",
      "transit",
      params?.corridor ?? null,
      params?.fromId ?? null,
      params?.toId ?? null,
      params?.lookback ?? null,
    ],
    queryFn: () => {
      if (!params?.fromId || !params?.toId) {
        throw new Error("fromId and toId are required to fetch transit metrics");
      }
      return fetchTransit(params);
    },
    enabled: Boolean(params?.fromId && params?.toId),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useCorridors = () =>
  useQuery({
    queryKey: ["open-sea", "corridors"],
    queryFn: fetchCorridors,
    staleTime: 60 * 60_000,
  });

export const useSeaStateSummary = (
  window: string = "h24",
  scope: "mediterranean" | "global" | "west_africa" = "mediterranean",
) =>
  useQuery({
    queryKey: ["open-sea", "sea-state-summary", window, scope],
    queryFn: () => fetchSeaStateSummary(window, scope),
    refetchInterval: appConfig.refreshSeconds * 1000,
  });

export const useMarketOil = (series: string[] = ["RBRTE", "RWTC"], range = "180d") =>
  useQuery({
    queryKey: ["market-oil", series.join(","), range],
    queryFn: () => fetchOil(series, range),
    staleTime: 6 * 60_000,
  });
