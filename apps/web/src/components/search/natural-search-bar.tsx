"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { SparklesIcon, LoaderIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { naturalSearch } from "@/lib/api/search";
import { toast } from "sonner";

export function NaturalSearchBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    try {
      const res = await naturalSearch({ query: trimmed });
      const constraints = res.parsed_constraints;

      const params = new URLSearchParams();
      if (constraints.origin) params.set("origin", String(constraints.origin));
      if (constraints.destination)
        params.set("destination", String(constraints.destination));
      if (constraints.departure_date)
        params.set("departure_date", String(constraints.departure_date));
      if (constraints.return_date)
        params.set("return_date", String(constraints.return_date));
      if (constraints.cabin_class)
        params.set("cabin_class", String(constraints.cabin_class));
      if (constraints.trip_type)
        params.set("trip_type", String(constraints.trip_type));

      params.set("natural", "1");
      params.set("q", trimmed);

      router.push(`/search?${params.toString()}`);
    } catch {
      toast.error("Failed to parse search query. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <div className="relative flex-1">
        <SparklesIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='e.g. "Seoul to Tokyo, March 15, one-way"'
          className="pl-9"
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={!query.trim() || loading}>
        {loading ? (
          <LoaderIcon className="size-4 animate-spin" />
        ) : (
          "Search"
        )}
      </Button>
    </form>
  );
}
