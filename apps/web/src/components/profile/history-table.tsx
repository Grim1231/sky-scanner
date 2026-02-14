"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getHistory } from "@/lib/api/users";
import type { SearchHistoryItem } from "@/lib/types";

export function HistoryTable() {
  const router = useRouter();
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const pageSize = 10;

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await getHistory(page, pageSize);
        if (!cancelled) {
          setItems(res.history);
          setTotal(res.total);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setItems([]);
          setTotal(0);
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [page]);

  const totalPages = Math.ceil(total / pageSize);

  function handleRowClick(item: SearchHistoryItem) {
    const params = new URLSearchParams({
      origin: item.origin,
      destination: item.destination,
      departure_date: item.departure_date,
      cabin_class: item.cabin_class,
      passengers: String(item.passengers),
    });
    if (item.return_date) params.set("return_date", item.return_date);
    router.push(`/search?${params}`);
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">No search history yet.</p>
        <p className="text-sm text-muted-foreground mt-1">
          Your flight searches will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Origin</TableHead>
            <TableHead>Destination</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-center">Passengers</TableHead>
            <TableHead>Cabin</TableHead>
            <TableHead className="text-center">Results</TableHead>
            <TableHead>Searched At</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow
              key={item.id}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => handleRowClick(item)}
            >
              <TableCell className="font-medium">{item.origin}</TableCell>
              <TableCell className="font-medium">{item.destination}</TableCell>
              <TableCell>{item.departure_date}</TableCell>
              <TableCell className="text-center">{item.passengers}</TableCell>
              <TableCell className="capitalize">
                {item.cabin_class.toLowerCase().replace("_", " ")}
              </TableCell>
              <TableCell className="text-center">
                {item.results_count}
              </TableCell>
              <TableCell>
                {format(new Date(item.searched_at), "yyyy-MM-dd HH:mm")}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} ({total} total)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
