import { apiFetch } from "@/lib/api-client";
import type {
  PriceHistoryResponse,
  PricePredictionResponse,
  BestTimeResponse,
  CabinClass,
} from "@/lib/types";

export async function getPriceHistory(params: {
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  cabin_class?: CabinClass;
  currency?: string;
}): Promise<PriceHistoryResponse> {
  const sp = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
    start_date: params.start_date,
    end_date: params.end_date,
  });
  if (params.cabin_class) sp.set("cabin_class", params.cabin_class);
  if (params.currency) sp.set("currency", params.currency);
  return apiFetch<PriceHistoryResponse>(`/prices/history?${sp}`);
}

export async function predictPrice(params: {
  origin: string;
  destination: string;
  departure_date: string;
  cabin_class?: CabinClass;
}): Promise<PricePredictionResponse> {
  const sp = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
    departure_date: params.departure_date,
  });
  if (params.cabin_class) sp.set("cabin_class", params.cabin_class);
  return apiFetch<PricePredictionResponse>(`/prices/predict?${sp}`);
}

export async function getBestTime(params: {
  origin: string;
  destination: string;
}): Promise<BestTimeResponse> {
  const sp = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
  });
  return apiFetch<BestTimeResponse>(`/prices/best-time?${sp}`);
}
