import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Plus, Trash2, Save, Loader2 } from "lucide-react";
import { DAY_LABELS } from "@/types/campaign";
import { fetchScheduleDetail, updateScheduleById, fetchScheduleTypes } from "@/lib/api/schedules";
import type { ScheduleTypeOption } from "@/lib/api/schedules";
import { toast } from "sonner";

const TIMEZONES = [
  "Africa/Addis_Ababa", "UTC", "Africa/Nairobi", "Africa/Cairo", "Africa/Lagos",
  "Europe/London", "America/New_York", "Asia/Dubai",
];

interface FormState {
  schedule_type: string;
  start_date: string;
  end_date: string;
  run_days: number[];
  time_windows: { start: string; end: string }[];
  timezone: string;
  auto_reset: boolean;
}

export default function ScheduleEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState | null>(null);
  const [campaignName, setCampaignName] = useState("");
  const [scheduleTypes, setScheduleTypes] = useState<ScheduleTypeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetchScheduleDetail(Number(id)),
      fetchScheduleTypes().catch(() => [
        { value: "once", display: "One Time" },
        { value: "daily", display: "Daily" },
        { value: "weekly", display: "Weekly" },
        { value: "monthly", display: "Monthly" },
      ]),
    ]).then(([detail, types]) => {
      setForm({
        schedule_type: detail.schedule_type,
        start_date: detail.start_date,
        end_date: detail.end_date || "",
        run_days: detail.run_days || [],
        time_windows: detail.time_windows.map(tw => ({ ...tw })),
        timezone: detail.timezone,
        auto_reset: detail.auto_reset,
      });
      setCampaignName(detail.campaign_name);
      setScheduleTypes(types);
    }).catch(e => {
      toast.error("Failed to load schedule");
      console.error(e);
    }).finally(() => setLoading(false));
  }, [id]);

  if (loading || !form) {
    return <div className="space-y-4 max-w-3xl"><Skeleton className="h-8 w-48" /><Skeleton className="h-96" /></div>;
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => prev ? { ...prev, [key]: value } : prev);
    setErrors(prev => { const { [key]: _, ...rest } = prev; return rest; });
  }

  function toggleDay(day: number) {
    if (!form) return;
    update("run_days", form.run_days.includes(day) ? form.run_days.filter(d => d !== day) : [...form.run_days, day].sort());
  }

  function updateTimeWindow(index: number, field: "start" | "end", value: string) {
    if (!form) return;
    const windows = [...form.time_windows];
    windows[index] = { ...windows[index], [field]: value };
    update("time_windows", windows);
  }

  function addTimeWindow() {
    if (!form) return;
    update("time_windows", [...form.time_windows, { start: "", end: "" }]);
  }

  function removeTimeWindow(index: number) {
    if (!form || form.time_windows.length <= 1) return;
    update("time_windows", form.time_windows.filter((_, i) => i !== index));
  }

  function validate(): boolean {
    if (!form) return false;
    const errs: Record<string, string> = {};
    if (!form.start_date) errs.start_date = "Start date is required";
    if (form.schedule_type !== "once" && !form.end_date) errs.end_date = "End date is required";
    if (form.schedule_type === "weekly" && form.run_days.length === 0) errs.run_days = "Select at least one day";
    for (let i = 0; i < form.time_windows.length; i++) {
      const tw = form.time_windows[i];
      if (!tw.start || !tw.end) { errs[`tw_${i}`] = "Both times required"; continue; }
      if (tw.start >= tw.end) errs[`tw_${i}`] = "Start must be before end";
    }
    const sorted = [...form.time_windows].filter(tw => tw.start && tw.end).sort((a, b) => a.start.localeCompare(b.start));
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].start < sorted[i - 1].end) errs.tw_overlap = "Time windows overlap";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit() {
    if (!form || !validate()) return;
    setSubmitting(true);
    try {
      const data: Record<string, unknown> = {
        schedule_type: form.schedule_type,
        start_date: form.start_date,
        end_date: form.end_date || null,
        time_windows: form.time_windows,
        timezone: form.timezone,
        auto_reset: form.auto_reset,
      };
      if (form.schedule_type === "weekly") data.run_days = form.run_days;
      await updateScheduleById(Number(id), data);
      toast.success("Schedule updated successfully");
      navigate(`/schedules/${id}`);
    } catch (e: any) {
      toast.error(e.message || "Failed to update schedule");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <button onClick={() => navigate(`/schedules/${id}`)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-1">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Schedule
        </button>
        <h1 className="text-2xl font-semibold tracking-tight">Edit Schedule</h1>
        <p className="text-sm text-muted-foreground mt-1">Campaign: {campaignName}</p>
      </div>

      <Card className="p-6 shadow-card space-y-6">
        <div className="space-y-2">
          <Label>Schedule Type</Label>
          <Select value={form.schedule_type} onValueChange={v => update("schedule_type", v)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {(scheduleTypes.length > 0 ? scheduleTypes : [
                { value: "once", display: "One Time" }, { value: "daily", display: "Daily" },
                { value: "weekly", display: "Weekly" }, { value: "monthly", display: "Monthly" },
              ]).map(t => <SelectItem key={t.value} value={t.value}>{t.display}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Start Date <span className="text-destructive">*</span></Label>
            <Input type="date" value={form.start_date} onChange={e => update("start_date", e.target.value)} />
            {errors.start_date && <p className="text-xs text-destructive">{errors.start_date}</p>}
          </div>
          <div className="space-y-2">
            <Label>End Date {form.schedule_type !== "once" && <span className="text-destructive">*</span>}</Label>
            <Input type="date" value={form.end_date} onChange={e => update("end_date", e.target.value)} />
            {errors.end_date && <p className="text-xs text-destructive">{errors.end_date}</p>}
          </div>
        </div>

        {form.schedule_type === "weekly" && (
          <div className="space-y-2">
            <Label>Run Days <span className="text-destructive">*</span></Label>
            <div className="flex flex-wrap gap-3">
              {[0, 1, 2, 3, 4, 5, 6].map(d => (
                <label key={d} className="flex items-center gap-2 text-sm cursor-pointer select-none">
                  <Checkbox checked={form.run_days.includes(d)} onCheckedChange={() => toggleDay(d)} />
                  {DAY_LABELS[d]}
                </label>
              ))}
            </div>
            {errors.run_days && <p className="text-xs text-destructive">{errors.run_days}</p>}
          </div>
        )}

        <div className="space-y-3">
          <Label>Time Windows <span className="text-destructive">*</span></Label>
          {form.time_windows.map((tw, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="flex items-center gap-2 flex-1">
                <Input type="time" value={tw.start} onChange={e => updateTimeWindow(i, "start", e.target.value)} />
                <span className="text-muted-foreground shrink-0">to</span>
                <Input type="time" value={tw.end} onChange={e => updateTimeWindow(i, "end", e.target.value)} />
              </div>
              {form.time_windows.length > 1 && (
                <Button type="button" variant="ghost" size="icon" className="h-9 w-9 text-destructive shrink-0" onClick={() => removeTimeWindow(i)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
          {errors.tw_overlap && <p className="text-xs text-destructive">{errors.tw_overlap}</p>}
          {Object.entries(errors).filter(([k]) => k.startsWith("tw_") && k !== "tw_overlap").map(([k, v]) => (
            <p key={k} className="text-xs text-destructive">{v}</p>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addTimeWindow} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" /> Add Time Window
          </Button>
        </div>

        <div className="space-y-2">
          <Label>Timezone</Label>
          <Select value={form.timezone} onValueChange={v => update("timezone", v)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {TIMEZONES.map(tz => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label>Auto Reset</Label>
            <p className="text-xs text-muted-foreground">Automatically reset after completion</p>
          </div>
          <Switch checked={form.auto_reset} onCheckedChange={v => update("auto_reset", v)} />
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="outline" onClick={() => navigate(`/schedules/${id}`)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} className="gap-1.5">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Changes
          </Button>
        </div>
      </Card>
    </div>
  );
}
