import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DAY_LABELS } from "@/types/campaign";
import { toast } from "sonner";
import { ArrowLeft, Pencil, Power, PowerOff, RotateCcw, Trash2, CalendarDays, Clock, Globe, RefreshCw } from "lucide-react";
import {
  fetchScheduleDetail, fetchUpcomingWindows, activateSchedule, deactivateSchedule,
  resetSchedule, deleteScheduleById,
} from "@/lib/api/schedules";
import type { ApiScheduleDetail } from "@/lib/api/schedules";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  stopped: "bg-red-50 text-red-700 border-red-200",
};

export default function ScheduleDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [schedule, setSchedule] = useState<ApiScheduleDetail | null>(null);
  const [upcoming, setUpcoming] = useState<{ date: string; windows: number[]; type: string; day_name?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => { if (id) loadData(); }, [id]);

  async function loadData() {
    setLoading(true);
    try {
      const [detail, upcomingRes] = await Promise.all([
        fetchScheduleDetail(Number(id)),
        fetchUpcomingWindows(Number(id), 10).catch(() => []),
      ]);
      setSchedule(detail);
      setUpcoming(upcomingRes);
    } catch (e) {
      console.error("Failed to load schedule", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleActivate() {
    try { await activateSchedule(Number(id)); await loadData(); toast.success("Schedule activated"); } catch (e: any) { toast.error(e.message); }
  }
  async function handleDeactivate() {
    try { await deactivateSchedule(Number(id)); await loadData(); toast.success("Schedule deactivated"); } catch (e: any) { toast.error(e.message); }
  }
  async function handleReset() {
    try { await resetSchedule(Number(id)); await loadData(); toast.success("Schedule reset"); } catch (e: any) { toast.error(e.message); }
  }
  async function handleDelete() {
    try { await deleteScheduleById(Number(id)); toast.success("Schedule deleted"); navigate("/schedules"); } catch (e: any) { toast.error(e.message); }
  }

  if (loading) {
    return <div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-64" /></div>;
  }

  if (!schedule) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-lg mb-4">Schedule not found</p>
        <Link to="/schedules"><Button variant="outline">Back to Schedules</Button></Link>
      </div>
    );
  }

  const s = schedule;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link to="/schedules" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-2">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Schedules
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">{s.campaign_name}</h1>
          <p className="text-sm text-muted-foreground mt-1">{s.schedule_summary}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {s.is_active ? (
            <Button variant="outline" size="sm" onClick={handleDeactivate} className="gap-1.5"><PowerOff className="h-3.5 w-3.5" /> Deactivate</Button>
          ) : (
            <Button variant="outline" size="sm" onClick={handleActivate} className="gap-1.5"><Power className="h-3.5 w-3.5" /> Activate</Button>
          )}
          <Button variant="outline" size="sm" onClick={handleReset} className="gap-1.5"><RotateCcw className="h-3.5 w-3.5" /> Reset</Button>
          <Button variant="outline" size="sm" onClick={() => navigate(`/schedules/${id}/edit`)} className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-destructive hover:text-destructive" onClick={() => setShowDelete(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase mb-1">Status</p>
          <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${s.is_active ? "text-emerald-600" : "text-muted-foreground"}`}>
            <span className={`h-2 w-2 rounded-full ${s.is_active ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
            {s.is_active ? "Active" : "Inactive"}
          </span>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase mb-1">Current Round</p>
          <p className="text-2xl font-semibold">{s.current_round}</p>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase mb-1">Windows Completed</p>
          <p className="text-2xl font-semibold">{s.total_windows_completed}</p>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase mb-1">Next Run</p>
          <p className="text-sm font-medium">{s.next_run_date || "—"}</p>
        </Card>
      </div>

      {/* Campaign Info */}
      {s.campaign_info && (
        <Card className="p-5 shadow-card">
          <h3 className="text-sm font-semibold mb-3">Campaign Info</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Name</p>
              <p className="font-medium">{s.campaign_info.name}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <Badge className={`text-xs border ${STATUS_COLORS[s.campaign_info.status] ?? "bg-muted"}`}>{s.campaign_info.status}</Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Execution</p>
              <p className="font-medium">{s.campaign_info.execution_status}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Campaign ID</p>
              <Link to={`/campaigns/${s.campaign_info.id}`} className="font-medium text-primary hover:underline">#{s.campaign_info.id}</Link>
            </div>
          </div>
        </Card>
      )}

      {/* Schedule Configuration */}
      <Card className="p-5 shadow-card space-y-4">
        <h3 className="text-sm font-semibold">Schedule Configuration</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <CalendarDays className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Schedule Type</p>
              <p className="font-medium">{s.schedule_type_display}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <CalendarDays className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Date Range</p>
              <p className="font-medium">{s.start_date} → {s.end_date || "No end date"}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Globe className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Timezone</p>
              <p className="font-medium">{s.timezone}</p>
            </div>
          </div>
        </div>

        {/* Run Days */}
        {s.schedule_type === "weekly" && s.run_days?.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">Run Days</p>
            <div className="flex flex-wrap gap-2">
              {s.run_days.map(d => (
                <Badge key={d} variant="secondary" className="text-xs">{DAY_LABELS[d]}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Time Windows */}
        <div>
          <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> Time Windows</p>
          <div className="flex flex-wrap gap-2">
            {s.time_windows.map((tw, i) => (
              <Badge key={i} variant="outline" className="text-xs font-mono">{tw.start} → {tw.end}</Badge>
            ))}
          </div>
        </div>

        {/* Auto Reset */}
        <div className="flex items-center gap-2 text-sm">
          <RefreshCw className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Auto Reset:</span>
          <span className="font-medium">{s.auto_reset ? "Enabled" : "Disabled"}</span>
        </div>
      </Card>

      {/* Upcoming Windows */}
      {upcoming.length > 0 && (
        <Card className="p-5 shadow-card">
          <h3 className="text-sm font-semibold mb-3">Upcoming Windows</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 pr-4 text-xs text-muted-foreground font-medium">Date</th>
                  <th className="text-left py-2 pr-4 text-xs text-muted-foreground font-medium">Day</th>
                  <th className="text-left py-2 pr-4 text-xs text-muted-foreground font-medium">Type</th>
                  <th className="text-left py-2 text-xs text-muted-foreground font-medium">Windows</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.map((w, i) => (
                  <tr key={i} className="border-b last:border-b-0">
                    <td className="py-2 pr-4 font-medium">{w.date}</td>
                    <td className="py-2 pr-4 text-muted-foreground">{w.day_name || "—"}</td>
                    <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{w.type}</Badge></td>
                    <td className="py-2">{w.windows.map(idx => s.time_windows[idx] ? `${s.time_windows[idx].start}-${s.time_windows[idx].end}` : `#${idx}`).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Completed Windows */}
      {Array.isArray(s.completed_windows) && s.completed_windows.length > 0 && (
        <Card className="p-5 shadow-card">
          <h3 className="text-sm font-semibold mb-3">Completed Windows</h3>
          <div className="text-sm text-muted-foreground">
            {s.completed_windows.length} window(s) completed
          </div>
        </Card>
      )}

      {/* Metadata */}
      <Card className="p-5 shadow-card">
        <h3 className="text-sm font-semibold mb-3">Metadata</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Created</p>
            <p className="font-medium">{new Date(s.created_at).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Updated</p>
            <p className="font-medium">{new Date(s.updated_at).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Last Processed</p>
            <p className="font-medium">{s.last_processed_at ? new Date(s.last_processed_at).toLocaleString() : "Never"}</p>
          </div>
        </div>
      </Card>

      {/* Delete Dialog */}
      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete the schedule for <strong>{s.campaign_name}</strong>? This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
