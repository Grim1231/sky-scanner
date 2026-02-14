"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { predictPrice } from "@/lib/api/prices";
import type { PricePredictionResponse } from "@/lib/types";

interface PredictionCardProps {
  origin: string;
  destination: string;
  departureDate?: string;
}

const formatKRW = (amount: number) =>
  new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);

const recommendationConfig = {
  BUY_NOW: { label: "Buy Now", variant: "default" as const, className: "bg-green-600 hover:bg-green-700" },
  WAIT: { label: "Wait", variant: "default" as const, className: "bg-yellow-500 hover:bg-yellow-600" },
  NEUTRAL: { label: "Neutral", variant: "secondary" as const, className: "" },
} as const;

export function PredictionCard({
  origin,
  destination,
  departureDate,
}: PredictionCardProps) {
  const [data, setData] = useState<PricePredictionResponse | null>(null);
  const [loading, setLoading] = useState(!!departureDate);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!departureDate) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setData(null);

    (async () => {
      try {
        const result = await predictPrice({
          origin,
          destination,
          departure_date: departureDate,
        });
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load prediction"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [origin, destination, departureDate]);

  if (!departureDate) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Price Prediction</CardTitle>
          <CardDescription>
            Select a departure date to see price predictions
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-36" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Price Prediction</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const config = recommendationConfig[data.recommendation];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Price Prediction
          <Badge variant={config.variant} className={config.className}>
            {config.label}
          </Badge>
        </CardTitle>
        <CardDescription>
          {data.days_until_departure} days until departure
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm">{data.reason}</p>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Current Avg</p>
            <p className="font-semibold">{formatKRW(data.current_avg_price)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Confidence</p>
            <p className="font-semibold">{Math.round(data.confidence * 100)}%</p>
          </div>
          <div>
            <p className="text-muted-foreground">Best Seen</p>
            <p className="font-semibold text-green-600">
              {formatKRW(data.best_price_seen)}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Worst Seen</p>
            <p className="font-semibold text-red-500">
              {formatKRW(data.worst_price_seen)}
            </p>
          </div>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-1">
            Current price percentile
          </p>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-all"
              style={{ width: `${data.percentile_current}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {Math.round(data.percentile_current)}th percentile
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
