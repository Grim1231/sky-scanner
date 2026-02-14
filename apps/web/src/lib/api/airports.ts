import { apiFetch } from "@/lib/api-client";
import type { AirportSearchResponse } from "@/lib/types";

export async function searchAirports(
  query: string,
  limit: number = 10
): Promise<AirportSearchResponse> {
  const sp = new URLSearchParams({ q: query, limit: String(limit) });
  return apiFetch<AirportSearchResponse>(`/airports/search?${sp}`);
}
