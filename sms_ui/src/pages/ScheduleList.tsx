import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import ListViewToggle, { useListView } from "@/components/ListViewToggle";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, CalendarClock, Eye, ChevronLeft, ChevronRight, Trash2, Power, PowerOff, Filter, X } from "lucide-react";
import { DAY_LABELS } from "@/types/campaign";
import { fetchSchedules, fetchScheduleSummary, deleteScheduleById, activateSchedule, deactivateSchedule } from "@/lib/api/schedules";
import type { ApiScheduleListItem, ScheduleSummary } from "@/lib/api/schedules";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const WINDOW_STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
};

const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  stopped: "bg-red-50 text-red-700 border-red-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
  expired: "bg-muted text-muted-foreground border-border",
};

export default function ScheduleList() {
  const navigate = useNavigate();
  const [view, setView] = useListView("schedules-view");
  const [schedules, setSchedules] = useState<ApiScheduleListItem[]>([]);
  const [summary, setSummary] = useState<ScheduleSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<ApiScheduleListItem | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [showFilters, setShowFilters] = useState(false);
  const pageSize = 10;

  useEffect(() => { loadData(); }, [page, filters]);

  async function loadData() {
    setLoading(true);
    try {
      const [listRes, summaryRes] = await Promise.all([
        fetchSchedules(page, pageSize, filters),
        page === 1 ? fetchScheduleSummary() : Promise.resolve(null),
      ]);
      setSchedules(listRes.results);
      setTotalCount(listRes.count);
      if (summaryRes) setSummary(summaryRes);
    } catch (e) {
      console.error("Failed to load schedules", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteScheduleById(deleteTarget.id);
      toast.success("Schedule deleted successfully");
      setDeleteTarget(null);
      loadData();
    } catch (e: any) {
      toast.error(e.message || "Failed to delete schedule");
    }
  }

  async function handleToggleActive(s: ApiScheduleListItem) {
    try {
      if (s.is_active) {
        await deactivateSchedule(s.id);
        toast.success("Schedule deactivated");
      } else {
        await activateSchedule(s.id);
        toast.success("Schedule activated");
      }
      loadData();
    } catch (e: any) {
      toast.error(e.message || "Failed to toggle schedule");
    }
  }

  function updateFilter(key: string, value: string) {
    setPage(1);
    setFilters(prev => {
      if (!value || value === "all") {
        const { [key]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [key]: value };
    });
  }

  function clearFilters() {
    setFilters({});
    setPage(1);
  }

  const hasFilters = Object.keys(filters).length > 0;
  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Schedules</h1>
          <p className="text-sm text-muted-foreground mt-1">Campaign scheduling and timing configuration</p>
        </div>
        <div className="flex items-center gap-2">
          <ListViewToggle view={view} onChange={setView} />
          <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)} className="gap-1.5">
            <Filter className="h-3.5 w-3.5" />
            Filters
            {hasFilters && <Badge variant="secondary" className="ml-1 h-5 w-5 p-0 flex items-center justify-center text-[10px]">{Object.keys(filters).length}</Badge>}
          </Button>
          <Button onClick={() => navigate("/schedules/create")} className="gap-2 shadow-soft">
            <Plus className="h-4 w-4" /> New Schedule
          </Button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card className="p-4 shadow-card">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Schedule Type</label>
              <Select value={filters.schedule_type || "all"} onValueChange={v => updateFilter("schedule_type", v)}>
                <SelectTrigger className="w-36 h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="once">One Time</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Campaign Status</label>
              <Select value={filters.campaign_status || "all"} onValueChange={v => updateFilter("campaign_status", v)}>
                <SelectTrigger className="w-36 h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                  <SelectItem value="stopped">Stopped</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="expired">Expired</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Active Status</label>
              <Select value={filters.is_active || "all"} onValueChange={v => updateFilter("is_active", v)}>
                <SelectTrigger className="w-36 h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="true">Active</SelectItem>
                  <SelectItem value="false">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {hasFilters && (
              <div className="flex items-end">
                <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1 text-muted-foreground h-9 mt-auto">
                  <X className="h-3.5 w-3.5" /> Clear
                </Button>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Schedules</p>
            <p className="text-2xl font-semibold">{summary.total_schedules}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Active</p>
            <p className="text-2xl font-semibold text-emerald-600">{summary.active_schedules}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Running Today</p>
            <p className="text-2xl font-semibold text-blue-600">{summary.running_today}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Inactive</p>
            <p className="text-2xl font-semibold text-muted-foreground">{summary.inactive_schedules}</p>
          </Card>
        </div>
      )}

      {view === "list" ? <Card className="shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Campaign</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Type</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Summary</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Campaign Status</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Next Run</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Active</th>
                <th className="text-right px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="px-5 py-3.5"><Skeleton className="h-4 w-20" /></td>
                  ))}
                </tr>
              ))}
              {!loading && schedules.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-16 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
                        <CalendarClock className="h-6 w-6 text-muted-foreground" />
                      </div>
                      <p className="text-muted-foreground">No schedules found.</p>
                      <Button variant="outline" size="sm" onClick={() => navigate("/schedules/create")} className="mt-2 gap-1.5">
                        <Plus className="h-3.5 w-3.5" /> Create Schedule
                      </Button>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && schedules.map((s) => (
                <tr key={s.id} className="border-b last:border-b-0 hover:bg-accent/50 transition-colors">
                  <td className="px-5 py-3.5 font-medium">{s.campaign_name}</td>
                  <td className="px-5 py-3.5">
                    <Badge variant="outline" className="text-xs">{s.schedule_type_display}</Badge>
                  </td>
                  <td className="px-5 py-3.5 text-muted-foreground text-xs max-w-[250px] truncate">{s.schedule_summary}</td>
                  <td className="px-5 py-3.5">
                    <Badge className={`text-xs border ${CAMPAIGN_STATUS_COLORS[s.campaign_status] ?? "bg-muted text-muted-foreground"}`}>
                      {s.campaign_status_display}
                    </Badge>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">{s.next_run_date || "—"}</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${s.is_active ? "text-emerald-600" : "text-muted-foreground"}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${s.is_active ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
                      {s.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="icon" className="h-8 w-8" title={s.is_active ? "Deactivate" : "Activate"} onClick={() => handleToggleActive(s)}>
                        {s.is_active ? <PowerOff className="h-3.5 w-3.5" /> : <Power className="h-3.5 w-3.5" />}
                      </Button>
                      <Link to={`/schedules/${s.id}`}>
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="View Details">
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" title="Delete" onClick={() => setDeleteTarget(s)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t bg-muted/20">
            <p className="text-xs text-muted-foreground">
              Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount}
            </p>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card> : loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => <Card key={index} className="p-5"><Skeleton className="h-5 w-40" /><Skeleton className="mt-4 h-4 w-full" /></Card>)}
        </div>
      ) : schedules.length === 0 ? (
        <Card className="p-12 text-center text-muted-foreground">No schedules found.</Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {schedules.map((s) => (
            <Card key={s.id} className="flex min-h-[220px] flex-col justify-between gap-4 p-5 shadow-card">
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><p className="font-semibold truncate">{s.campaign_name}</p><p className="mt-1 text-xs text-muted-foreground">Schedule #{s.id}</p></div>
                  <Badge variant="outline" className="shrink-0 text-xs">{s.schedule_type_display}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">{s.schedule_summary}</p>
                <div className="flex items-center justify-between gap-2">
                  <Badge className={`text-xs border ${CAMPAIGN_STATUS_COLORS[s.campaign_status] ?? "bg-muted text-muted-foreground"}`}>{s.campaign_status_display}</Badge>
                  <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${s.is_active ? "text-emerald-600" : "text-muted-foreground"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${s.is_active ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />{s.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">Next run: {s.next_run_date || "—"}</p>
              </div>
              <div className="flex justify-end gap-1 border-t pt-2">
                <Button variant="ghost" size="icon" className="h-8 w-8" title={s.is_active ? "Deactivate" : "Activate"} onClick={() => handleToggleActive(s)}>{s.is_active ? <PowerOff className="h-3.5 w-3.5" /> : <Power className="h-3.5 w-3.5" />}</Button>
                <Link to={`/schedules/${s.id}`}><Button variant="ghost" size="icon" className="h-8 w-8" title="View Details"><Eye className="h-3.5 w-3.5" /></Button></Link>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="Delete" onClick={() => setDeleteTarget(s)}><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete the schedule for <strong>{deleteTarget?.campaign_name}</strong>? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
