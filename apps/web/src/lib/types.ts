// ── Enums ──────────────────────────────────────────────────────────────────

export type CabinClass = "ECONOMY" | "PREMIUM_ECONOMY" | "BUSINESS" | "FIRST";
export type TripType = "ONE_WAY" | "ROUND_TRIP" | "MULTI_CITY";
export type DataSource = "GOOGLE_PROTOBUF" | "KIWI_API" | "DIRECT_CRAWL" | "GDS";
export type PriceRecommendation = "BUY_NOW" | "WAIT" | "NEUTRAL";

// ── Search ─────────────────────────────────────────────────────────────────

export interface PassengerCount {
  adults: number;
  children: number;
  infants_in_seat: number;
  infants_on_lap: number;
}

export interface FlightSearchRequest {
  origin: string;
  destination: string;
  departure_date: string; // YYYY-MM-DD
  return_date?: string;
  cabin_class: CabinClass;
  trip_type: TripType;
  passengers: PassengerCount;
  currency: string;
  include_alternatives: boolean;
}

export interface PriceInfo {
  amount: number;
  currency: string;
  source: string;
  fare_class?: string;
  booking_url?: string;
  includes_baggage: boolean;
  includes_meal: boolean;
  crawled_at: string; // ISO datetime
}

export interface FlightResult {
  flight_number: string;
  airline_code: string;
  airline_name: string;
  origin: string;
  destination: string;
  origin_city: string;
  destination_city: string;
  departure_time: string; // ISO datetime
  arrival_time: string;
  duration_minutes: number;
  cabin_class: string;
  aircraft_type?: string;
  prices: PriceInfo[];
  lowest_price?: number;
  source: string;
  score?: number;
  score_breakdown?: Record<string, number>;
}

export interface FlightSearchResponse {
  flights: FlightResult[];
  total: number;
  cached: boolean;
  background_crawl_dispatched: boolean;
}

// ── Natural Search ─────────────────────────────────────────────────────────

export interface NaturalSearchRequest {
  query: string;
}

export interface NaturalSearchResponse {
  parsed_constraints: Record<string, unknown>;
  flights: FlightResult[];
  total: number;
  cached: boolean;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export interface RegisterRequest {
  email: string;
  name: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── User ────────────────────────────────────────────────────────────────────

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface UserPreferenceResponse {
  min_seat_pitch?: number;
  min_seat_width?: number;
  preferred_departure_time_start?: string; // HH:MM:SS
  preferred_departure_time_end?: string;
  max_layover_hours?: number;
  max_stops?: number;
  preferred_alliance?: string;
  preferred_airlines?: Record<string, boolean>;
  excluded_airlines?: Record<string, boolean>;
  baggage_required: boolean;
  meal_required: boolean;
  preferred_cabin_class?: string;
  priority: string;
  notes?: string;
}

export interface UpdatePreferenceRequest {
  min_seat_pitch?: number;
  min_seat_width?: number;
  preferred_departure_time_start?: string;
  preferred_departure_time_end?: string;
  max_layover_hours?: number;
  max_stops?: number;
  preferred_alliance?: string;
  preferred_airlines?: Record<string, boolean>;
  excluded_airlines?: Record<string, boolean>;
  baggage_required?: boolean;
  meal_required?: boolean;
  preferred_cabin_class?: string;
  priority?: string;
  notes?: string;
}

export interface SearchHistoryItem {
  id: string;
  origin: string;
  destination: string;
  departure_date: string;
  return_date?: string;
  passengers: number;
  cabin_class: string;
  searched_at: string;
  results_count: number;
}

export interface SearchHistoryResponse {
  history: SearchHistoryItem[];
  total: number;
}

// ── Airport ─────────────────────────────────────────────────────────────────

export interface AirportItem {
  code: string;
  name: string;
  city: string;
  country: string;
  timezone: string;
  latitude: number;
  longitude: number;
}

export interface AirportSearchResponse {
  query: string;
  airports: AirportItem[];
  total: number;
}

// ── Airline ─────────────────────────────────────────────────────────────────

export interface AirlineItem {
  code: string;
  name: string;
  type: string;
  alliance: string;
  base_country: string;
  website_url?: string;
}

export interface AirlineListResponse {
  airlines: AirlineItem[];
  total: number;
}

// ── Price ────────────────────────────────────────────────────────────────────

export interface PricePoint {
  date: string;
  min_price: number;
  max_price: number;
  avg_price: number;
  currency: string;
  sample_count: number;
}

export interface PriceHistoryResponse {
  origin: string;
  destination: string;
  cabin_class: CabinClass;
  currency: string;
  price_points: PricePoint[];
  total_points: number;
}

export interface PricePredictionResponse {
  origin: string;
  destination: string;
  departure_date: string;
  cabin_class: string;
  current_avg_price: number;
  predicted_direction: string;
  confidence: number;
  recommendation: PriceRecommendation;
  reason: string;
  best_price_seen: number;
  worst_price_seen: number;
  percentile_current: number;
  days_until_departure: number;
}

export interface BestTimeResponse {
  origin: string;
  destination: string;
  optimal_days_before: number;
  estimated_price_at_optimal?: number;
  confidence: number;
  current_days_before: number;
  recommendation: string;
}

// ── Error ───────────────────────────────────────────────────────────────────

export interface ErrorResponse {
  detail: string;
  code?: string;
}
