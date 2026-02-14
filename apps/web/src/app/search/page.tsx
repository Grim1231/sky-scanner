import { Suspense } from "react";
import { SearchContent } from "./search-content";
import { Skeleton } from "@/components/ui/skeleton";

function SearchFallback() {
  return (
    <div className="container mx-auto px-4 py-6 space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <div className="space-y-3 mt-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full" />
        ))}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchFallback />}>
      <SearchContent />
    </Suspense>
  );
}
