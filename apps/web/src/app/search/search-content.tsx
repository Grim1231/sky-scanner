"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRightIcon, BarChart3Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FlightList } from "@/components/results/flight-list";
import { searchFlights } from "@/lib/api/search";
import { toast } from "sonner";
import type {
  CabinClass,
  FlightResult,
  TripType,
} from "@/lib/types";

const CABIN_LABELS: Record<string, string> = {
  ECONOMY: "Economy",
  PREMIUM_ECONOMY: "Premium Economy",
  BUSINESS: "Business",
  FIRST: "First",
};

export function SearchContent() {
  const searchParams = useSearchParams();
  const [flights, setFlights] = useState<FlightResult[]>([]);
  const [loading, setLoading] = useState(true);

  const origin = searchParams.get("origin") ?? "";
  const destination = searchParams.get("destination") ?? "";
  const departureDate = searchParams.get("departure_date") ?? "";
  const returnDate = searchParams.get("return_date") ?? undefined;
  const cabinClass = (searchParams.get("cabin_class") ?? "ECONOMY") as CabinClass;
  const tripType = (searchParams.get("trip_type") ?? "ONE_WAY") as TripType;
  const adults = Number(searchParams.get("passengers_adults") ?? "1");
  const children = Number(searchParams.get("passengers_children") ?? "0");
  const infantsSeat = Number(searchParams.get("passengers_infants_in_seat") ?? "0");
  const infantsLap = Number(searchParams.get("passengers_infants_on_lap") ?? "0");
  const totalPassengers = adults + children + infantsSeat + infantsLap;

  useEffect(() => {
    if (!origin || !destination || !departureDate) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function doSearch() {
      setLoading(true);
      try {
        const res = await searchFlights({
          origin,
          destination,
          departure_date: departureDate,
          return_date: returnDate,
          cabin_class: cabinClass,
          trip_type: tripType,
          passengers: {
            adults,
            children,
            infants_in_seat: infantsSeat,
            infants_on_lap: infantsLap,
          },
          currency: "KRW",
          include_alternatives: false,
        });

        if (!cancelled) {
          setFlights(res.flights);
          if (res.background_crawl_dispatched) {
            toast.info("Searching for more flights in the background...");
          }
        }
      } catch {
        if (!cancelled) {
          toast.error("Failed to search flights. Please try again.");
          setFlights([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    doSearch();
    return () => {
      cancelled = true;
    };
  }, [
    origin,
    destination,
    departureDate,
    returnDate,
    cabinClass,
    tripType,
    adults,
    children,
    infantsSeat,
    infantsLap,
  ]);

  return (
    <div className="container mx-auto px-4 py-6">
      {/* Search summary */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            {origin}
            <ArrowRightIcon className="size-4" />
            {destination}
          </h1>
          <p className="text-sm text-muted-foreground">
            {departureDate}
            {returnDate ? ` - ${returnDate}` : ""}
            {" \u00B7 "}
            {totalPassengers} {totalPassengers === 1 ? "passenger" : "passengers"}
            {" \u00B7 "}
            {CABIN_LABELS[cabinClass] ?? cabinClass}
          </p>
        </div>
        {origin && destination && (
          <Button variant="outline" size="sm" asChild>
            <Link href={`/prices/${origin}/${destination}`}>
              <BarChart3Icon className="size-4" />
              Price Analysis
            </Link>
          </Button>
        )}
      </div>

      <FlightList flights={flights} isLoading={loading} />
    </div>
  );
}
