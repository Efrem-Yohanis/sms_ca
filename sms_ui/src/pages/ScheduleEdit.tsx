import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import StepSchedule, { type ScheduleStepData } from "@/components/wizard/StepSchedule";
import { fetchScheduleDetail, updateScheduleById } from "@/lib/api/schedules";
import { toast } from "sonner";

const ETHIOPIAN_TIMEZONE = "Africa/Addis_Ababa";

export default function ScheduleEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<ScheduleStepData | null>(null);
  const [campaignName, setCampaignName] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!id) return;
    fetchScheduleDetail(Number(id)).then((detail) => {
      setForm({
        schedule_type: detail.schedule_type as ScheduleStepData["schedule_type"],
        start_date: detail.start_date,
        end_date: detail.end_date || "",
        run_days: detail.run_days || [],
        time_windows: detail.time_windows.map((window) => ({ ...window })),
        auto_reset: detail.auto_reset,
      });
      setCampaignName(detail.campaign_name);
    }).catch((error) => {
      toast.error("Failed to load schedule");
      console.error(error);
    }).finally(() => setLoading(false));
  }, [id]);

  function updateSchedule(partial: Partial<ScheduleStepData>) {
    setForm((previous) => previous ? { ...previous, ...partial } : previous);
    setErrors({});
  }

  function validate(data: ScheduleStepData) {
    const next: Record<string, string> = {};
    if (!data.start_date) next.start_date = "Start date is required";
    if (data.schedule_type === "weekly" && !data.run_days.length) next.run_days = "Select at least one day";
    if (!data.time_windows.length || data.time_windows.some((window) => !window.start || !window.end || window.start >= window.end)) {
      next.time_windows = "Enter valid start and end times for every window";
    } else {
      const ordered = [...data.time_windows].sort((a, b) => a.start.localeCompare(b.start));
      if (ordered.some((window, index) => index > 0 && window.start < ordered[index - 1].end)) {
        next.time_windows = "Time windows cannot overlap";
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit() {
    if (!form || !validate(form)) return;
    setSubmitting(true);
    try {
      await updateScheduleById(Number(id), {
        schedule_type: form.schedule_type,
        start_date: form.start_date,
        end_date: form.end_date || null,
        run_days: form.schedule_type === "weekly" ? form.run_days : [],
        time_windows: form.time_windows,
        timezone: ETHIOPIAN_TIMEZONE,
        auto_reset: form.auto_reset,
      });
      toast.success("Schedule updated successfully");
      navigate(`/schedules/${id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update schedule");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !form) return <div className="max-w-3xl space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-96" /></div>;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <button onClick={() => navigate(`/schedules/${id}`)} className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Schedule
        </button>
        <h1 className="text-2xl font-semibold tracking-tight">Edit Schedule</h1>
        <p className="mt-1 text-sm text-muted-foreground">Campaign: {campaignName} · Schedule times use Ethiopian time.</p>
      </div>
      <Card className="space-y-6 p-6 shadow-card">
        <StepSchedule data={form} errors={errors} update={updateSchedule} />
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="outline" onClick={() => navigate(`/schedules/${id}`)}>Cancel</Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting} className="gap-1.5">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Changes
          </Button>
        </div>
      </Card>
    </div>
  );
}
