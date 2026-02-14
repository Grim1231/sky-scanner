"use client";

import { use } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PriceChart } from "@/components/prices/price-chart";
import { PredictionCard } from "@/components/prices/prediction-card";
import { BestTimeCard } from "@/components/prices/best-time-card";

export default function PriceAnalysisPage({
  params,
}: {
  params: Promise<{ origin: string; dest: string }>;
}) {
  const { origin, dest } = use(params);
  const searchParams = useSearchParams();
  const departureDate = searchParams.get("departure_date") ?? undefined;

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href="/search"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to search
        </Link>
        <h1 className="text-2xl font-bold">
          {origin.toUpperCase()} &rarr; {dest.toUpperCase()} Price Analysis
        </h1>
      </div>

      <PriceChart origin={origin} destination={dest} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <PredictionCard
          origin={origin}
          destination={dest}
          departureDate={departureDate}
        />
        <BestTimeCard origin={origin} destination={dest} />
      </div>
    </div>
  );
}
