"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { ArrowRightLeftIcon, SearchIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AirportCombobox } from "@/components/search/airport-combobox";
import { DatePicker } from "@/components/search/date-picker";
import { PassengerSelector } from "@/components/search/passenger-selector";
import { CabinClassSelect } from "@/components/search/cabin-class-select";
import type { AirportItem, CabinClass, PassengerCount, TripType } from "@/lib/types";

export function SearchForm() {
  const router = useRouter();
  const [origin, setOrigin] = useState<AirportItem | null>(null);
  const [destination, setDestination] = useState<AirportItem | null>(null);
  const [departureDate, setDepartureDate] = useState<Date | undefined>();
  const [returnDate, setReturnDate] = useState<Date | undefined>();
  const [tripType, setTripType] = useState<TripType>("ONE_WAY");
  const [cabinClass, setCabinClass] = useState<CabinClass>("ECONOMY");
  const [passengers, setPassengers] = useState<PassengerCount>({
    adults: 1,
    children: 0,
    infants_in_seat: 0,
    infants_on_lap: 0,
  });

  const swapAirports = () => {
    const tmp = origin;
    setOrigin(destination);
    setDestination(tmp);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!origin || !destination || !departureDate) return;

    const params = new URLSearchParams({
      origin: origin.code,
      destination: destination.code,
      departure_date: format(departureDate, "yyyy-MM-dd"),
      cabin_class: cabinClass,
      trip_type: tripType,
      passengers_adults: String(passengers.adults),
      passengers_children: String(passengers.children),
      passengers_infants_in_seat: String(passengers.infants_in_seat),
      passengers_infants_on_lap: String(passengers.infants_on_lap),
    });

    if (tripType === "ROUND_TRIP" && returnDate) {
      params.set("return_date", format(returnDate, "yyyy-MM-dd"));
    }

    router.push(`/search?${params.toString()}`);
  };

  const today = new Date();

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Trip type toggle */}
      <div className="flex gap-2">
        <Button
          type="button"
          variant={tripType === "ONE_WAY" ? "default" : "outline"}
          size="sm"
          onClick={() => {
            setTripType("ONE_WAY");
            setReturnDate(undefined);
          }}
        >
          One-way
        </Button>
        <Button
          type="button"
          variant={tripType === "ROUND_TRIP" ? "default" : "outline"}
          size="sm"
          onClick={() => setTripType("ROUND_TRIP")}
        >
          Round trip
        </Button>
      </div>

      {/* Origin / Destination */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-2 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">From</label>
          <AirportCombobox
            value={origin}
            onChange={setOrigin}
            placeholder="Origin airport"
          />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={swapAirports}
          className="self-end"
        >
          <ArrowRightLeftIcon className="size-4" />
        </Button>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">To</label>
          <AirportCombobox
            value={destination}
            onChange={setDestination}
            placeholder="Destination airport"
          />
        </div>
      </div>

      {/* Dates / Passengers / Cabin */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Departure</label>
          <DatePicker
            date={departureDate}
            onChange={setDepartureDate}
            placeholder="Departure date"
            minDate={today}
          />
        </div>
        {tripType === "ROUND_TRIP" && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Return</label>
            <DatePicker
              date={returnDate}
              onChange={setReturnDate}
              placeholder="Return date"
              minDate={departureDate ?? today}
            />
          </div>
        )}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Passengers</label>
          <PassengerSelector value={passengers} onChange={setPassengers} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Cabin</label>
          <CabinClassSelect value={cabinClass} onChange={setCabinClass} />
        </div>
      </div>

      <Button
        type="submit"
        size="lg"
        disabled={!origin || !destination || !departureDate}
        className="w-full md:w-auto md:self-end"
      >
        <SearchIcon className="size-4" />
        Search Flights
      </Button>
    </form>
  );
}
