"use client";

import { format } from "date-fns";
import { ExternalLinkIcon, PlaneIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ScoreBadge } from "@/components/results/score-badge";
import type { FlightResult } from "@/lib/types";

interface FlightCardProps {
  flight: FlightResult;
}

function formatDuration(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const priceFormatter = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  maximumFractionDigits: 0,
});

export function FlightCard({ flight }: FlightCardProps) {
  const departure = new Date(flight.departure_time);
  const arrival = new Date(flight.arrival_time);
  const bestPrice = flight.lowest_price ?? flight.prices[0]?.amount;
  const bookingUrl = flight.prices[0]?.booking_url;

  return (
    <Card className="py-4">
      <CardContent className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        {/* Airline + flight number */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex size-10 items-center justify-center rounded-full bg-muted shrink-0">
            <PlaneIcon className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="font-medium text-sm truncate">
              {flight.airline_name}
            </div>
            <div className="text-xs text-muted-foreground">
              {flight.flight_number} &middot; {flight.cabin_class}
            </div>
          </div>
        </div>

        {/* Times */}
        <div className="flex items-center gap-4 text-sm">
          <div className="text-center">
            <div className="font-semibold">{format(departure, "HH:mm")}</div>
            <div className="text-xs text-muted-foreground">{flight.origin}</div>
          </div>
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-xs text-muted-foreground">
              {formatDuration(flight.duration_minutes)}
            </span>
            <div className="h-px w-16 bg-border" />
          </div>
          <div className="text-center">
            <div className="font-semibold">{format(arrival, "HH:mm")}</div>
            <div className="text-xs text-muted-foreground">
              {flight.destination}
            </div>
          </div>
        </div>

        {/* Score + Price */}
        <div className="flex items-center gap-3 md:flex-col md:items-end">
          <div className="flex items-center gap-2">
            {flight.score != null && (
              <ScoreBadge
                score={flight.score}
                breakdown={flight.score_breakdown}
              />
            )}
            {bestPrice != null && (
              <span className="font-semibold text-lg whitespace-nowrap">
                {priceFormatter.format(bestPrice)}
              </span>
            )}
          </div>
          {bookingUrl && (
            <Button variant="outline" size="sm" asChild>
              <a href={bookingUrl} target="_blank" rel="noopener noreferrer">
                Book
                <ExternalLinkIcon className="size-3" />
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
