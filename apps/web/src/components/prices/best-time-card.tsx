"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getBestTime } from "@/lib/api/prices";
import type { BestTimeResponse } from "@/lib/types";

interface BestTimeCardProps {
  origin: string;
  destination: string;
}

const formatKRW = (amount: number) =>
  new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);

export function BestTimeCard({ origin, destination }: BestTimeCardProps) {
  const [data, setData] = useState<BestTimeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBestTime({ origin, destination })
      .then(setData)
      .catch((err) =>
        setError(err.message ?? "Failed to load best time data")
      )
      .finally(() => setLoading(false));
  }, [origin, destination]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Best Time to Buy</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const optimalPosition = Math.min(
    100,
    Math.max(0, (data.optimal_days_before / Math.max(data.optimal_days_before, data.current_days_before, 1)) * 100)
  );
  const currentPosition = Math.min(
    100,
    Math.max(0, (data.current_days_before / Math.max(data.optimal_days_before, data.current_days_before, 1)) * 100)
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Best Time to Buy</CardTitle>
        <CardDescription>Optimal purchase timing analysis</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Optimal Days Before</p>
            <p className="text-2xl font-bold">{data.optimal_days_before}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Current Days Before</p>
            <p className="text-2xl font-bold">{data.current_days_before}</p>
          </div>
          {data.estimated_price_at_optimal != null && (
            <div>
              <p className="text-muted-foreground">Est. Price at Optimal</p>
              <p className="font-semibold">
                {formatKRW(data.estimated_price_at_optimal)}
              </p>
            </div>
          )}
          <div>
            <p className="text-muted-foreground">Confidence</p>
            <p className="font-semibold">
              {Math.round(data.confidence * 100)}%
            </p>
          </div>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-2">
            Timing indicator
          </p>
          <div className="relative h-3 rounded-full bg-muted">
            <div
              className="absolute top-0 h-full w-1 rounded-full bg-green-500"
              style={{ left: `${optimalPosition}%` }}
              title="Optimal"
            />
            <div
              className="absolute top-0 h-full w-1 rounded-full bg-blue-500"
              style={{ left: `${currentPosition}%` }}
              title="Current"
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>Departure</span>
            <span>
              <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1" />
              Optimal
              <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mx-1 ml-3" />
              Now
            </span>
          </div>
        </div>

        <p className="text-sm">{data.recommendation}</p>
      </CardContent>
    </Card>
  );
}
