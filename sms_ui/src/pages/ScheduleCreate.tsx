import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import StepSchedule, { type ScheduleStepData } from "@/components/wizard/StepSchedule";
import { createSchedule } from "@/lib/api/schedules";
import { toast } from "sonner";

const ETHIOPIAN_TIMEZONE = "Africa/Addis_Ababa";
type FormState = ScheduleStepData & { campaign: string };

const initialForm: FormState = {
  campaign: "",
  schedule_type: "once",
  start_date: "",
  end_date: "",
  run_days: [],
  time_windows: [{ start: "", end: "" }],
  auto_reset: true,
};

export default function ScheduleCreate() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function updateSchedule(partial: Partial<ScheduleStepData>) {
    setForm((previous) => ({ ...previous, ...partial }));
    setErrors({});
  }

  function validate() {
    const next: Record<string, string> = {};
    if (!form.campaign.trim() || !Number.isInteger(Number(form.campaign))) next.campaign = "Enter a valid campaign ID";
    if (!form.start_date) next.start_date = "Start date is required";
    if (form.schedule_type === "weekly" && !form.run_days.length) next.run_days = "Select at least one day";
    if (!form.time_windows.length || form.time_windows.some((window) => !window.start || !window.end || window.start >= window.end)) {
      next.time_windows = "Enter valid start and end times for every window";
    } else {
      const ordered = [...form.time_windows].sort((a, b) => a.start.localeCompare(b.start));
      if (ordered.some((window, index) => index > 0 && window.start < ordered[index - 1].end)) {
        next.time_windows = "Time windows cannot overlap";
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setSubmitting(true);
    try {
      const campaignId = Number(form.campaign);
      await createSchedule(campaignId, {
        schedule_type: form.schedule_type,
        start_date: form.start_date,
        ...(form.end_date ? { end_date: form.end_date } : {}),
        ...(form.schedule_type === "weekly" ? { run_days: form.run_days } : {}),
        time_windows: form.time_windows,
        timezone: ETHIOPIAN_TIMEZONE,
        auto_reset: form.auto_reset,
      });
      toast.success("Schedule created successfully");
      navigate(`/campaigns/${campaignId}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create schedule");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <button onClick={() => navigate("/schedules")} className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Schedules
        </button>
        <h1 className="text-2xl font-semibold tracking-tight">Create Schedule</h1>
        <p className="mt-1 text-sm text-muted-foreground">Schedule times use Ethiopian time.</p>
      </div>
      <Card className="space-y-6 p-6 shadow-card">
        <div className="space-y-1.5">
          <Label htmlFor="campaign">Campaign ID</Label>
          <Input id="campaign" type="number" placeholder="Enter campaign ID" value={form.campaign} onChange={(event) => setForm((previous) => ({ ...previous, campaign: event.target.value }))} />
          {errors.campaign && <p className="text-sm text-destructive">{errors.campaign}</p>}
        </div>
        <StepSchedule data={form} errors={errors} update={updateSchedule} />
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="outline" onClick={() => navigate("/schedules")}>Cancel</Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting} className="gap-1.5">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Create Schedule
          </Button>
        </div>
      </Card>
    </div>
  );
}
