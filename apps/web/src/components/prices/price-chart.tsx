"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { format, subDays } from "date-fns";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getPriceHistory } from "@/lib/api/prices";
import type { PricePoint } from "@/lib/types";

interface PriceChartProps {
  origin: string;
  destination: string;
}

const formatKRW = (amount: number) =>
  new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);

export function PriceChart({ origin, destination }: PriceChartProps) {
  const [data, setData] = useState<PricePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const endDate = new Date();
    const startDate = subDays(endDate, 30);

    getPriceHistory({
      origin,
      destination,
      start_date: format(startDate, "yyyy-MM-dd"),
      end_date: format(endDate, "yyyy-MM-dd"),
    })
      .then((res) => setData(res.price_points))
      .catch((err) => setError(err.message ?? "Failed to load price history"))
      .finally(() => setLoading(false));
  }, [origin, destination]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-32" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[300px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Price History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Price History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No price data available for this route.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Price History</CardTitle>
        <CardDescription>Last 30 days price trend</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="avgGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="rangeGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#93c5fd" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#93c5fd" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              tickFormatter={(v: string) => format(new Date(v), "MM/dd")}
              className="text-xs"
            />
            <YAxis
              tickFormatter={(v: number) => `${Math.round(v / 1000)}K`}
              className="text-xs"
            />
            <Tooltip
              formatter={(value: number | undefined) =>
                value != null ? formatKRW(value) : ""
              }
              labelFormatter={(label) =>
                format(new Date(String(label)), "yyyy-MM-dd")
              }
            />
            <Area
              type="monotone"
              dataKey="max_price"
              stroke="#93c5fd"
              fill="url(#rangeGradient)"
              strokeWidth={1}
              name="Max"
            />
            <Area
              type="monotone"
              dataKey="avg_price"
              stroke="#3b82f6"
              fill="url(#avgGradient)"
              strokeWidth={2}
              name="Avg"
            />
            <Area
              type="monotone"
              dataKey="min_price"
              stroke="#93c5fd"
              fill="url(#rangeGradient)"
              strokeWidth={1}
              name="Min"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
