import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  cinemoryApi,
  type Health,
  type Manifest,
  type Occasion,
  type ReelRequest,
  type ReelResponse,
} from "./api";

export const queryKeys = {
  health: ["health"] as const,
  occasions: ["occasions"] as const,
  manifest: (name: string) => ["manifest", name] as const,
};

export function useHealth(): UseQueryResult<Health> {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => cinemoryApi.health(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useOccasions(): UseQueryResult<Occasion[]> {
  return useQuery({
    queryKey: queryKeys.occasions,
    queryFn: () => cinemoryApi.occasions(),
    staleTime: 5 * 60_000,
  });
}

export function useManifest(name: string | null): UseQueryResult<Manifest | null> {
  return useQuery({
    queryKey: queryKeys.manifest(name ?? ""),
    queryFn: () => cinemoryApi.manifest(name as string),
    enabled: !!name,
    staleTime: Infinity,
  });
}

/** The reel-generation mutation. On success we prime the manifest cache so the
 *  provenance panel can render instantly from GET /reels/{name}. */
export function useCreateReel() {
  const qc = useQueryClient();
  return useMutation<ReelResponse, Error, ReelRequest>({
    mutationFn: (body) => cinemoryApi.createReel(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.manifest(data.reel_name) });
    },
  });
}
