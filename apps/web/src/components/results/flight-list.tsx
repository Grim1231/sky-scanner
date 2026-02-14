"use client";

import { useState, useCallback } from "react";
import { PlaneIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { FlightCard } from "@/components/results/flight-card";
import { SortSelect } from "@/components/results/sort-select";
import { FilterSidebar } from "@/components/results/filter-sidebar";
import type { FlightResult } from "@/lib/types";

interface FlightListProps {
  flights: FlightResult[];
  isLoading: boolean;
}

function sortFlights(flights: FlightResult[], sort: string): FlightResult[] {
  const sorted = [...flights];
  switch (sort) {
    case "price_asc":
      sorted.sort(
        (a, b) => (a.lowest_price ?? Infinity) - (b.lowest_price ?? Infinity)
      );
      break;
    case "price_desc":
      sorted.sort(
        (a, b) => (b.lowest_price ?? 0) - (a.lowest_price ?? 0)
      );
      break;
    case "duration_asc":
      sorted.sort((a, b) => a.duration_minutes - b.duration_minutes);
      break;
    case "departure_asc":
      sorted.sort(
        (a, b) =>
          new Date(a.departure_time).getTime() -
          new Date(b.departure_time).getTime()
      );
      break;
    case "recommended":
    default:
      sorted.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
      break;
  }
  return sorted;
}

function FlightCardSkeleton() {
  return (
    <div className="rounded-xl border p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="space-y-1.5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-16" />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Skeleton className="h-5 w-10" />
          <Skeleton className="h-px w-16" />
          <Skeleton className="h-5 w-10" />
        </div>
        <div className="flex items-center gap-3">
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-8 w-16" />
        </div>
      </div>
    </div>
  );
}

export function FlightList({ flights, isLoading }: FlightListProps) {
  const [sort, setSort] = useState("recommended");
  const [filteredFlights, setFilteredFlights] = useState<FlightResult[]>(flights);

  const handleFilter = useCallback((filtered: FlightResult[]) => {
    setFilteredFlights(filtered);
  }, []);

  const sorted = sortFlights(filteredFlights, sort);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <FlightCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      <FilterSidebar flights={flights} onFilter={handleFilter} />
      <div className="flex-1 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {sorted.length} {sorted.length === 1 ? "flight" : "flights"} found
          </span>
          <SortSelect value={sort} onChange={setSort} />
        </div>

        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <PlaneIcon className="size-10 mb-3 opacity-40" />
            <p className="font-medium">No flights found</p>
            <p className="text-sm">Try adjusting your filters or search criteria</p>
          </div>
        ) : (
          sorted.map((flight, i) => (
            <FlightCard key={`${flight.flight_number}-${i}`} flight={flight} />
          ))
        )}
      </div>
    </div>
  );
}
