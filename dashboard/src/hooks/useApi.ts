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
} from "../api/client";
import type { Basin } from "../api/types";
import { appConfig } from "../config";

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
