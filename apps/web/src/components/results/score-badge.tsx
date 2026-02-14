"use client";

import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number;
  breakdown?: Record<string, number>;
}

function scoreColor(score: number) {
  if (score >= 80) return "bg-green-500/15 text-green-700 border-green-500/30";
  if (score >= 60) return "bg-yellow-500/15 text-yellow-700 border-yellow-500/30";
  return "bg-red-500/15 text-red-700 border-red-500/30";
}

export function ScoreBadge({ score, breakdown }: ScoreBadgeProps) {
  const badge = (
    <Badge
      variant="outline"
      className={cn("tabular-nums cursor-default", scoreColor(score))}
    >
      {Math.round(score)}
    </Badge>
  );

  if (!breakdown || Object.keys(breakdown).length === 0) return badge;

  return (
    <Popover>
      <PopoverTrigger asChild>{badge}</PopoverTrigger>
      <PopoverContent className="w-56 p-3">
        <div className="text-sm font-medium mb-2">Score Breakdown</div>
        <div className="flex flex-col gap-1.5">
          {Object.entries(breakdown).map(([key, val]) => (
            <div key={key} className="flex justify-between text-sm">
              <span className="text-muted-foreground capitalize">
                {key.replace(/_/g, " ")}
              </span>
              <span className="font-medium tabular-nums">
                {typeof val === "number" ? val.toFixed(1) : val}
              </span>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
