import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WizardData, ScheduleType } from "@/types/campaign";
import { SCHEDULE_TYPE_LABELS, DAY_LABELS } from "@/types/campaign";
import { Plus, Trash2, Clock, Repeat, Calendar, CalendarRange, CalendarDays } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  data: WizardData;
  errors: Record<string, string>;
  update: (partial: Partial<WizardData>) => void;
}

const SCHEDULE_TYPES: { value: ScheduleType; icon: typeof Clock; desc: string }[] = [
  { value: "once", icon: Clock, desc: "Send once at a specific date & time" },
  { value: "daily", icon: Calendar, desc: "Repeat every day" },
  { value: "weekly", icon: CalendarRange, desc: "Repeat on selected days each week" },
  { value: "monthly", icon: CalendarDays, desc: "Repeat monthly" },
];

const TIMEZONE_OPTIONS = [
  "UTC",
  "Africa/Addis_Ababa",
  "Africa/Nairobi",
  "Europe/London",
  "America/New_York",
];

export default function StepSchedule({ data, errors, update }: Props) {
  const isRecurring = data.schedule_type !== "once";

  function setScheduleType(type: ScheduleType) {
    update({
      schedule_type: type,
      ...(type === "once" && { run_days: [], end_date: "" }),
    });
  }

  function toggleDay(day: number) {
    const current = data.run_days;
    const updated = current.includes(day)
      ? current.filter((d) => d !== day)
      : [...current, day].sort();
    update({ run_days: updated });
  }

  function addTimeWindow() {
    update({ time_windows: [...data.time_windows, { start: "", end: "" }] });
  }

  function removeTimeWindow(index: number) {
    if (data.time_windows.length <= 1) return;
    update({ time_windows: data.time_windows.filter((_, i) => i !== index) });
  }

  function updateWindow(index: number, field: "start" | "end", value: string) {
    const windows = [...data.time_windows];
    windows[index] = { ...windows[index], [field]: value };
    update({ time_windows: windows });
  }

  return (
    <div className="space-y-5">
      {/* Schedule type selector */}
      <div className="space-y-1.5">
        <Label>Schedule type</Label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {SCHEDULE_TYPES.map(({ value, icon: Icon, desc }) => (
            <button
              key={value}
              type="button"
              onClick={() => setScheduleType(value)}
              className={cn(
                "flex flex-col items-start gap-1 border rounded-sm p-3 transition-colors text-left",
                data.schedule_type === value
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "border-border hover:border-muted-foreground"
              )}
            >
              <Icon className={cn("h-4 w-4", data.schedule_type === value ? "text-primary" : "text-muted-foreground")} />
              <p className={cn("font-medium text-sm", data.schedule_type === value ? "text-primary" : "text-foreground")}>
                {SCHEDULE_TYPE_LABELS[value]}
              </p>
              <p className="text-xs text-muted-foreground leading-tight">{desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Start date (always required) */}
      <div className={cn("grid gap-4", isRecurring ? "grid-cols-2" : "grid-cols-1")}>
        <div className="space-y-1.5">
          <Label htmlFor="startDate">{isRecurring ? "Start date" : "Send date"}</Label>
          <Input
            id="startDate"
            type="date"
            value={data.start_date}
            onChange={(e) => update({ start_date: e.target.value })}
          />
          {errors.start_date && <p className="text-sm text-destructive">{errors.start_date}</p>}
        </div>

        {isRecurring && (
          <div className="space-y-1.5">
            <Label htmlFor="endDate">End date <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Input
              id="endDate"
              type="date"
              value={data.end_date}
              onChange={(e) => update({ end_date: e.target.value })}
            />
            {errors.end_date && <p className="text-sm text-destructive">{errors.end_date}</p>}
          </div>
        )}
      </div>

      {/* Run days (weekly only) */}
      {data.schedule_type === "weekly" && (
        <div className="space-y-1.5">
          <Label>Run days</Label>
          <div className="flex flex-wrap gap-3 pt-1">
            {Object.entries(DAY_LABELS).map(([key, label]) => {
              const day = Number(key);
              return (
                <div key={day} className="flex items-center gap-1.5">
                  <Checkbox
                    id={`day-${day}`}
                    checked={data.run_days.includes(day)}
                    onCheckedChange={() => toggleDay(day)}
                  />
                  <Label htmlFor={`day-${day}`} className="font-normal cursor-pointer text-sm">
                    {label.slice(0, 3)}
                  </Label>
                </div>
              );
            })}
          </div>
          {errors.run_days && <p className="text-sm text-destructive">{errors.run_days}</p>}
        </div>
      )}

      {/* Time windows (always required) */}
      <div className="space-y-2">
        <Label>Time windows</Label>
        {data.time_windows.map((tw, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input
              type="time"
              value={tw.start}
              onChange={(e) => updateWindow(i, "start", e.target.value)}
              className="w-36"
            />
            <span className="text-muted-foreground text-sm">to</span>
            <Input
              type="time"
              value={tw.end}
              onChange={(e) => updateWindow(i, "end", e.target.value)}
              className="w-36"
            />
            {data.time_windows.length > 1 && (
              <button onClick={() => removeTimeWindow(i)} className="text-destructive hover:text-destructive/80">
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={addTimeWindow}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add time window
        </Button>
        {errors.time_windows && <p className="text-sm text-destructive">{errors.time_windows}</p>}
      </div>

      {/* Timezone */}
      <div className="space-y-1.5">
        <Label>Timezone</Label>
        <Select value={data.timezone} onValueChange={(v) => update({ timezone: v })}>
          <SelectTrigger className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIMEZONE_OPTIONS.map((tz) => (
              <SelectItem key={tz} value={tz}>{tz}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Auto reset */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="autoReset"
          checked={data.auto_reset}
          onCheckedChange={(v) => update({ auto_reset: !!v })}
        />
        <Label htmlFor="autoReset" className="font-normal cursor-pointer text-sm">
          Auto-reset for next window
        </Label>
      </div>
    </div>
  );
}
