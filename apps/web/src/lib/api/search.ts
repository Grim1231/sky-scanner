import { apiFetch } from "@/lib/api-client";
import type {
  FlightSearchRequest,
  FlightSearchResponse,
  NaturalSearchRequest,
  NaturalSearchResponse,
} from "@/lib/types";

export async function searchFlights(
  req: FlightSearchRequest
): Promise<FlightSearchResponse> {
  return apiFetch<FlightSearchResponse>("/search/flights", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function naturalSearch(
  req: NaturalSearchRequest
): Promise<NaturalSearchResponse> {
  return apiFetch<NaturalSearchResponse>("/search/natural", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
