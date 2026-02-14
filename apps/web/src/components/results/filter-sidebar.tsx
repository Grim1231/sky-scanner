"use client";

import { useState, useEffect, useMemo } from "react";
import { FilterIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { FlightResult } from "@/lib/types";

interface FilterSidebarProps {
  flights: FlightResult[];
  onFilter: (filtered: FlightResult[]) => void;
}

interface Filters {
  stops: Set<string>;
  minPrice: string;
  maxPrice: string;
  airlines: Set<string>;
}

function defaultFilters(): Filters {
  return {
    stops: new Set(["nonstop", "1", "2+"]),
    minPrice: "",
    maxPrice: "",
    airlines: new Set<string>(),
  };
}

function applyFilters(flights: FlightResult[], filters: Filters): FlightResult[] {
  return flights.filter((f) => {
    // Price filter
    const price = f.lowest_price ?? f.prices[0]?.amount;
    if (price != null) {
      if (filters.minPrice && price < Number(filters.minPrice)) return false;
      if (filters.maxPrice && price > Number(filters.maxPrice)) return false;
    }

    // Airlines filter
    if (filters.airlines.size > 0 && !filters.airlines.has(f.airline_code))
      return false;

    return true;
  });
}

function FilterContent({
  flights,
  filters,
  setFilters,
}: {
  flights: FlightResult[];
  filters: Filters;
  setFilters: (f: Filters) => void;
}) {
  const airlines = useMemo(() => {
    const map = new Map<string, string>();
    for (const f of flights) {
      map.set(f.airline_code, f.airline_name);
    }
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [flights]);

  const toggleAirline = (code: string) => {
    const next = new Set(filters.airlines);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setFilters({ ...filters, airlines: next });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Price range */}
      <div>
        <Label className="text-sm font-medium">Price range</Label>
        <div className="flex gap-2 mt-1.5">
          <Input
            type="number"
            placeholder="Min"
            value={filters.minPrice}
            onChange={(e) =>
              setFilters({ ...filters, minPrice: e.target.value })
            }
          />
          <Input
            type="number"
            placeholder="Max"
            value={filters.maxPrice}
            onChange={(e) =>
              setFilters({ ...filters, maxPrice: e.target.value })
            }
          />
        </div>
      </div>

      <Separator />

      {/* Airlines */}
      {airlines.length > 0 && (
        <div>
          <Label className="text-sm font-medium">Airlines</Label>
          <div className="flex flex-col gap-1.5 mt-1.5 max-h-48 overflow-y-auto">
            {airlines.map(([code, name]) => (
              <label key={code} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={
                    filters.airlines.size === 0 || filters.airlines.has(code)
                  }
                  onChange={() => toggleAirline(code)}
                  className="rounded"
                />
                <span>
                  {name} ({code})
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      <Button
        variant="outline"
        size="sm"
        onClick={() => setFilters(defaultFilters())}
      >
        Reset filters
      </Button>
    </div>
  );
}

export function FilterSidebar({ flights, onFilter }: FilterSidebarProps) {
  const [filters, setFilters] = useState<Filters>(defaultFilters);

  useEffect(() => {
    onFilter(applyFilters(flights, filters));
  }, [flights, filters, onFilter]);

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden lg:block w-64 shrink-0">
        <div className="sticky top-20">
          <h3 className="font-medium mb-3">Filters</h3>
          <FilterContent
            flights={flights}
            filters={filters}
            setFilters={setFilters}
          />
        </div>
      </div>

      {/* Mobile sheet */}
      <div className="lg:hidden">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm">
              <FilterIcon className="size-4" />
              Filters
            </Button>
          </SheetTrigger>
          <SheetContent side="left">
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
            </SheetHeader>
            <div className="p-4">
              <FilterContent
                flights={flights}
                filters={filters}
                setFilters={setFilters}
              />
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
