"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CabinClass } from "@/lib/types";

interface CabinClassSelectProps {
  value: CabinClass;
  onChange: (cls: CabinClass) => void;
}

const CABIN_OPTIONS: { value: CabinClass; label: string }[] = [
  { value: "ECONOMY", label: "Economy" },
  { value: "PREMIUM_ECONOMY", label: "Premium Economy" },
  { value: "BUSINESS", label: "Business" },
  { value: "FIRST", label: "First" },
];

export function CabinClassSelect({ value, onChange }: CabinClassSelectProps) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as CabinClass)}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder="Cabin class" />
      </SelectTrigger>
      <SelectContent>
        {CABIN_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
