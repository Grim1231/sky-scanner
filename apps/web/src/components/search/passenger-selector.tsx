"use client";

import { UsersIcon, MinusIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { PassengerCount } from "@/lib/types";

interface PassengerSelectorProps {
  value: PassengerCount;
  onChange: (count: PassengerCount) => void;
}

const LABELS: { key: keyof PassengerCount; label: string; description: string }[] = [
  { key: "adults", label: "Adults", description: "12+ years" },
  { key: "children", label: "Children", description: "2-11 years" },
  { key: "infants_in_seat", label: "Infants (seat)", description: "Under 2, own seat" },
  { key: "infants_on_lap", label: "Infants (lap)", description: "Under 2, on lap" },
];

function totalPassengers(v: PassengerCount) {
  return v.adults + v.children + v.infants_in_seat + v.infants_on_lap;
}

export function PassengerSelector({ value, onChange }: PassengerSelectorProps) {
  const total = totalPassengers(value);

  const update = (key: keyof PassengerCount, delta: number) => {
    const next = { ...value, [key]: value[key] + delta };
    if (next[key] < 0) return;
    if (key === "adults" && next.adults < 1) return;
    if (totalPassengers(next) > 9) return;
    onChange(next);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-start font-normal">
          <UsersIcon className="mr-2 size-4" />
          {total} {total === 1 ? "Passenger" : "Passengers"}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start">
        <div className="flex flex-col gap-3">
          {LABELS.map(({ key, label, description }) => (
            <div key={key} className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{label}</div>
                <div className="text-xs text-muted-foreground">{description}</div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon-xs"
                  onClick={() => update(key, -1)}
                  disabled={
                    key === "adults" ? value[key] <= 1 : value[key] <= 0
                  }
                >
                  <MinusIcon className="size-3" />
                </Button>
                <span className="w-6 text-center text-sm">{value[key]}</span>
                <Button
                  variant="outline"
                  size="icon-xs"
                  onClick={() => update(key, 1)}
                  disabled={totalPassengers(value) >= 9}
                >
                  <PlusIcon className="size-3" />
                </Button>
              </div>
            </div>
          ))}
          <div className="text-xs text-muted-foreground text-right">
            Max 9 passengers
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
