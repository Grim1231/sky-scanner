"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ChevronsUpDownIcon, CheckIcon, PlaneIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { searchAirports } from "@/lib/api/airports";
import type { AirportItem } from "@/lib/types";

interface AirportComboboxProps {
  value: AirportItem | null;
  onChange: (airport: AirportItem | null) => void;
  placeholder: string;
}

export function AirportCombobox({
  value,
  onChange,
  placeholder,
}: AirportComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [airports, setAirports] = useState<AirportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const fetchAirports = useCallback(async (q: string) => {
    if (q.length < 2) {
      setAirports([]);
      return;
    }
    setLoading(true);
    try {
      const res = await searchAirports(q);
      setAirports(res.airports);
    } catch {
      setAirports([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchAirports(query), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchAirports]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          {value ? (
            <span className="truncate">
              {value.code} - {value.city}
            </span>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search airports..."
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            {loading ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Searching...
              </div>
            ) : query.length < 2 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Type at least 2 characters
              </div>
            ) : airports.length === 0 ? (
              <CommandEmpty>No airports found.</CommandEmpty>
            ) : (
              <CommandGroup>
                {airports.map((airport) => (
                  <CommandItem
                    key={airport.code}
                    value={airport.code}
                    onSelect={() => {
                      onChange(
                        airport.code === value?.code ? null : airport
                      );
                      setOpen(false);
                      setQuery("");
                    }}
                  >
                    <PlaneIcon className="size-4 shrink-0" />
                    <div className="flex flex-col">
                      <span className="font-medium">
                        {airport.code} - {airport.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {airport.city}, {airport.country}
                      </span>
                    </div>
                    <CheckIcon
                      className={cn(
                        "ml-auto size-4",
                        value?.code === airport.code
                          ? "opacity-100"
                          : "opacity-0"
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
