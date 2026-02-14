"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { getPreferences, updatePreferences } from "@/lib/api/users";
import type { UpdatePreferenceRequest } from "@/lib/types";

const CABIN_CLASSES = [
  { value: "ECONOMY", label: "Economy" },
  { value: "PREMIUM_ECONOMY", label: "Premium Economy" },
  { value: "BUSINESS", label: "Business" },
  { value: "FIRST", label: "First" },
];

const ALLIANCES = [
  { value: "", label: "None" },
  { value: "Star Alliance", label: "Star Alliance" },
  { value: "SkyTeam", label: "SkyTeam" },
  { value: "oneworld", label: "oneworld" },
];

const PRIORITIES = [
  { value: "PRICE", label: "Price" },
  { value: "DURATION", label: "Duration" },
  { value: "COMFORT", label: "Comfort" },
  { value: "BALANCED", label: "Balanced" },
];

const STOP_OPTIONS = [
  { value: "0", label: "Non-stop only" },
  { value: "1", label: "Up to 1 stop" },
  { value: "2", label: "Up to 2 stops" },
  { value: "3", label: "Up to 3 stops" },
];

export function PreferenceForm() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [cabinClass, setCabinClass] = useState("");
  const [maxStops, setMaxStops] = useState("");
  const [maxLayoverHours, setMaxLayoverHours] = useState("");
  const [baggageRequired, setBaggageRequired] = useState(false);
  const [mealRequired, setMealRequired] = useState(false);
  const [alliance, setAlliance] = useState("");
  const [priority, setPriority] = useState("BALANCED");
  const [departureStart, setDepartureStart] = useState("");
  const [departureEnd, setDepartureEnd] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    getPreferences()
      .then((prefs) => {
        if (prefs) {
          setCabinClass(prefs.preferred_cabin_class ?? "");
          setMaxStops(prefs.max_stops != null ? String(prefs.max_stops) : "");
          setMaxLayoverHours(
            prefs.max_layover_hours != null
              ? String(prefs.max_layover_hours)
              : ""
          );
          setBaggageRequired(prefs.baggage_required);
          setMealRequired(prefs.meal_required);
          setAlliance(prefs.preferred_alliance ?? "");
          setPriority(prefs.priority ?? "BALANCED");
          setDepartureStart(prefs.preferred_departure_time_start ?? "");
          setDepartureEnd(prefs.preferred_departure_time_end ?? "");
          setNotes(prefs.notes ?? "");
        }
      })
      .catch(() => {
        // Preferences may not exist yet, which is fine
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);

    const req: UpdatePreferenceRequest = {
      preferred_cabin_class: cabinClass || undefined,
      max_stops: maxStops ? Number(maxStops) : undefined,
      max_layover_hours: maxLayoverHours ? Number(maxLayoverHours) : undefined,
      baggage_required: baggageRequired,
      meal_required: mealRequired,
      preferred_alliance: alliance || undefined,
      priority: priority || undefined,
      preferred_departure_time_start: departureStart || undefined,
      preferred_departure_time_end: departureEnd || undefined,
      notes: notes || undefined,
    };

    try {
      await updatePreferences(req);
      toast.success("Preferences saved");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to save preferences";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-10 w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="cabinClass">Preferred Cabin Class</Label>
          <Select value={cabinClass} onValueChange={setCabinClass}>
            <SelectTrigger id="cabinClass">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              {CABIN_CLASSES.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="maxStops">Maximum Stops</Label>
          <Select value={maxStops} onValueChange={setMaxStops}>
            <SelectTrigger id="maxStops">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              {STOP_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="maxLayover">Max Layover (hours)</Label>
          <Input
            id="maxLayover"
            type="number"
            min={0}
            max={72}
            placeholder="No limit"
            value={maxLayoverHours}
            onChange={(e) => setMaxLayoverHours(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="alliance">Preferred Alliance</Label>
          <Select value={alliance} onValueChange={setAlliance}>
            <SelectTrigger id="alliance">
              <SelectValue placeholder="None" />
            </SelectTrigger>
            <SelectContent>
              {ALLIANCES.map((a) => (
                <SelectItem key={a.value || "none"} value={a.value || "none"}>
                  {a.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="priority">Priority</Label>
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger id="priority">
              <SelectValue placeholder="Balanced" />
            </SelectTrigger>
            <SelectContent>
              {PRIORITIES.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="departureStart">Preferred Departure (from)</Label>
          <Input
            id="departureStart"
            type="time"
            value={departureStart}
            onChange={(e) => setDepartureStart(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="departureEnd">Preferred Departure (to)</Label>
          <Input
            id="departureEnd"
            type="time"
            value={departureEnd}
            onChange={(e) => setDepartureEnd(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-6">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={baggageRequired}
            onChange={(e) => setBaggageRequired(e.target.checked)}
            className="rounded"
          />
          Baggage required
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={mealRequired}
            onChange={(e) => setMealRequired(e.target.checked)}
            className="rounded"
          />
          Meal required
        </label>
      </div>

      <div className="space-y-2">
        <Label htmlFor="notes">Notes</Label>
        <textarea
          id="notes"
          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          placeholder="Any additional preferences..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <Button type="submit" disabled={saving}>
        {saving ? "Saving..." : "Save Preferences"}
      </Button>
    </form>
  );
}
