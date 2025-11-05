import { useQuery } from "@tanstack/react-query";
import { fetchSIS, type SISResponse } from "../api/openSea";

/**
 * Hook to fetch SIS (Sea Impact Score) data for a corridor.
 * 
 * @param corridor - Corridor ID (e.g. "CHOKEPOINT_MALACCA->UNK")
 * @param window - Time window for data (default: "d7" for 7 days)
 * @returns Query result with SIS data
 */
export function useSISData(corridor: string | null | undefined, window: string = "d7") {
  return useQuery<SISResponse>({
    queryKey: ["sis", corridor, window],
    queryFn: async () => {
      if (!corridor) {
        return Promise.reject(new Error("No corridor specified"));
      }
      try {
        return await fetchSIS(corridor, window);
      } catch (error: any) {
        // Silently ignore 404 errors (corridor doesn't have data yet)
        if (error?.response?.status === 404 || error?.status === 404) {
          console.debug(`No SIS data available for corridor ${corridor}`);
          return null as any; // Return null instead of throwing
        }
        throw error; // Re-throw other errors
      }
    },
    enabled: !!corridor,
    refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
    staleTime: 2 * 60 * 1000, // Consider stale after 2 minutes
    retry: (failureCount, error: any) => {
      // Don't retry 404 errors
      if (error?.response?.status === 404 || error?.status === 404) {
        return false;
      }
      return failureCount < 2;
    },
  });
}
