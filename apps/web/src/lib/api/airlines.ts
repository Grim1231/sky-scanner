import { apiFetch } from "@/lib/api-client";
import type { AirlineListResponse } from "@/lib/types";

export async function getAirlines(params?: {
  type?: string;
  alliance?: string;
}): Promise<AirlineListResponse> {
  const sp = new URLSearchParams();
  if (params?.type) sp.set("type", params.type);
  if (params?.alliance) sp.set("alliance", params.alliance);
  const qs = sp.toString();
  return apiFetch<AirlineListResponse>(`/airlines${qs ? `?${qs}` : ""}`);
}
