import { useState, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchCampaigns, deleteCampaignApi, startCampaign, pauseCampaign, stopCampaign, type ApiCampaign } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import ListViewToggle, { useListView } from "@/components/ListViewToggle";
import {
  Plus, Search, Eye, Pencil, Trash2, ChevronLeft, ChevronRight,
  Play, Pause, Square, Clock, ArrowUpDown, RefreshCw,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  active: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800",
  paused: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  completed: "bg-primary/10 text-primary border-primary/20",
  archived: "bg-secondary text-secondary-foreground",
};

const EXEC_STYLES: Record<string, string> = {
  PENDING: "bg-muted text-muted-foreground",
  PROCESSING: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300",
  COMPLETED: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300",
  FAILED: "bg-destructive/10 text-destructive border-destructive/20",
  PAUSED: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300",
  STOPPED: "bg-muted text-muted-foreground",
};

type ActionType = "start" | "pause" | "stop" | "delete";

interface PendingAction {
  type: ActionType;
  campaignId: number;
  campaignName: string;
}

const ACTION_CONFIG: Record<ActionType, { title: string; description: string; buttonLabel: string; destructive: boolean }> = {
  start: { title: "Start campaign", description: "This will begin sending messages to all recipients.", buttonLabel: "Start", destructive: false },
  pause: { title: "Pause campaign", description: "This will temporarily pause message delivery. You can resume later.", buttonLabel: "Pause", destructive: false },
  stop: { title: "Stop campaign", description: "This will permanently stop the campaign. This action cannot be undone.", buttonLabel: "Stop", destructive: true },
  delete: { title: "Delete campaign", description: "This action cannot be undone. The campaign will be permanently removed.", buttonLabel: "Delete", destructive: true },
};

export default function CampaignList() {
  const [view, setView] = useListView("campaigns-view");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [execFilter, setExecFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 400);
    return () => clearTimeout(t);
  }, [searchInput]);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["campaigns", page, pageSize, statusFilter, execFilter, search, ordering],
    queryFn: () => fetchCampaigns({
      page,
      pageSize,
      status: statusFilter !== "all" ? statusFilter : undefined,
      execution_status: execFilter !== "all" ? execFilter : undefined,
      search: search || undefined,
      ordering,
    }),
    refetchInterval: 300000,
  });

  const campaigns = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const handleConfirmAction = useCallback(async () => {
    if (!pendingAction) return;
    setActionLoading(true);
    try {
      switch (pendingAction.type) {
        case "start":
          await startCampaign(pendingAction.campaignId);
          toast.success(`Campaign "${pendingAction.campaignName}" started`);
          break;
        case "pause":
          await pauseCampaign(pendingAction.campaignId);
          toast.success(`Campaign "${pendingAction.campaignName}" paused`);
          break;
        case "stop":
          await stopCampaign(pendingAction.campaignId);
          toast.success(`Campaign "${pendingAction.campaignName}" stopped`);
          break;
        case "delete":
          await deleteCampaignApi(pendingAction.campaignId);
          toast.success(`Campaign "${pendingAction.campaignName}" deleted`);
          break;
      }
      refetch();
    } catch (e: any) {
      toast.error(e.message || `Failed to ${pendingAction.type} campaign`);
    } finally {
      setActionLoading(false);
      setPendingAction(null);
    }
  }, [pendingAction, refetch]);

  const toggleOrdering = (field: string) => {
    setOrdering((prev) => prev === field ? `-${field}` : prev === `-${field}` ? field : `-${field}`);
    setPage(1);
  };

  const actionConfig = pendingAction ? ACTION_CONFIG[pendingAction.type] : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {totalCount} campaign{totalCount !== 1 ? "s" : ""} total
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => void refetch()}
            disabled={isFetching}
            aria-label="Refresh campaigns"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <ListViewToggle view={view} onChange={setView} />
          <Link to="/campaigns/new">
            <Button className="gap-2 shadow-soft">
              <Plus className="h-4 w-4" />
              Create campaign
            </Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative max-w-xs flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search campaigns..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="paused">Paused</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
        <Select value={execFilter} onValueChange={(v) => { setExecFilter(v); setPage(1); }}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Execution status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All execution</SelectItem>
            <SelectItem value="PENDING">Pending</SelectItem>
            <SelectItem value="PROCESSING">Processing</SelectItem>
            <SelectItem value="COMPLETED">Completed</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
            <SelectItem value="PAUSED">Paused</SelectItem>
            <SelectItem value="STOPPED">Stopped</SelectItem>
          </SelectContent>
        </Select>
        <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="10">10 / page</SelectItem>
            <SelectItem value="20">20 / page</SelectItem>
            <SelectItem value="50">50 / page</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Campaigns */}
      {isLoading ? (
        <Card className="shadow-card overflow-hidden">
          <div className="border-b bg-muted/50 px-5 py-3.5">
            <div className="grid grid-cols-8 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-3 w-16" />
              ))}
            </div>
          </div>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="border-b last:border-b-0 px-5 py-4">
              <div className="grid grid-cols-8 gap-4 items-center">
                {Array.from({ length: 8 }).map((_, j) => (
                  <Skeleton key={j} className="h-4 w-full" />
                ))}
              </div>
            </div>
          ))}
        </Card>
      ) : error ? (
        <Card className="shadow-card">
          <CardContent className="py-16 text-center">
            <p className="text-destructive mb-3">{(error as Error).message}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      ) : view === "list" ? (
        <Card className="shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  <SortableHeader label="Name" field="name" current={ordering} onToggle={toggleOrdering} />
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Status</th>
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Execution</th>
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Sender</th>
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Channels</th>
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider min-w-[180px]">Progress</th>
                  <SortableHeader label="Created" field="created_at" current={ordering} onToggle={toggleOrdering} />
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Next Run</th>
                  <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Ready</th>
                  <th className="text-right px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-5 py-16 text-center text-muted-foreground">
                      No campaigns found.
                    </td>
                  </tr>
                )}
                {campaigns.map((c) => (
                  <CampaignRow key={c.id} campaign={c} onAction={setPendingAction} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : campaigns.length === 0 ? (
        <Card className="shadow-card">
          <CardContent className="py-16 text-center text-muted-foreground">No campaigns found.</CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {campaigns.map((campaign) => (
            <CampaignGridCard key={campaign.id} campaign={campaign} onAction={setPendingAction} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} · {totalCount} campaigns
          </p>
          <div className="flex gap-1">
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Confirmation dialog for all actions */}
      <AlertDialog open={!!pendingAction} onOpenChange={() => setPendingAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{actionConfig?.title}</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingAction && (
                <>
                  <span className="font-medium text-foreground">{pendingAction.campaignName}</span>
                  <br />
                  {actionConfig?.description}
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={actionLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={actionConfig?.destructive ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" : ""}
              onClick={handleConfirmAction}
              disabled={actionLoading}
            >
              {actionLoading ? "Processing..." : actionConfig?.buttonLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/* ---- Sub-components ---- */

function SortableHeader({ label, field, current, onToggle }: {
  label: string; field: string; current: string; onToggle: (f: string) => void;
}) {
  const isActive = current === field || current === `-${field}`;
  const isDesc = current === `-${field}`;
  return (
    <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => onToggle(field)}>
        {label}
        <ArrowUpDown className={`h-3 w-3 ${isActive ? "text-foreground" : ""} ${isActive && !isDesc ? "rotate-180" : ""}`} />
      </button>
    </th>
  );
}

function CampaignRow({ campaign: c, onAction }: { campaign: ApiCampaign; onAction: (a: PendingAction) => void }) {
  const channels = Array.isArray(c.channels) ? c.channels : Object.values(c.channels || {});
  const progressPercent = (c as any).progress_percent ?? 0;
  const totalMessages = (c as any).total_messages ?? 0;
  const totalProcessed = (c as any).total_processed ?? 0;
  const nextRun = (c as any).next_run;
  const hasSchedule = (c as any).has_schedule;
  const hasAudience = (c as any).has_audience;
  const hasContent = (c as any).has_content;

  const triggerAction = (type: ActionType) => {
    onAction({ type, campaignId: c.id, campaignName: c.name });
  };

  return (
    <tr className="border-b last:border-b-0 hover:bg-accent/50 transition-colors">
      <td className="px-5 py-3.5 font-medium">
        <Link to={`/campaigns/${c.id}`} className="hover:text-primary transition-colors">
          {c.name}
        </Link>
      </td>
      <td className="px-5 py-3.5">
        <Badge className={`${STATUS_STYLES[c.status] || STATUS_STYLES.draft} text-xs border`}>
          {(c as any).status_display || c.status}
        </Badge>
      </td>
      <td className="px-5 py-3.5">
        {c.execution_status_display ? (
          <Badge className={`${EXEC_STYLES[c.execution_status] || ""} text-xs border`}>
            {c.execution_status_display}
          </Badge>
        ) : "—"}
      </td>
      <td className="px-5 py-3.5 text-muted-foreground">{c.sender_id || "—"}</td>
      <td className="px-5 py-3.5">
        <div className="flex gap-1 flex-wrap">
          {channels.map((ch: string) => (
            <Badge key={ch} variant="secondary" className="text-xs">
              {ch === "sms" ? "SMS" : ch === "app_notification" ? "App" : ch}
            </Badge>
          ))}
        </div>
      </td>
      <td className="px-5 py-3.5">
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{totalProcessed.toLocaleString()} / {totalMessages.toLocaleString()}</span>
            <span>{progressPercent.toFixed(0)}%</span>
          </div>
          <Progress value={progressPercent} className="h-1.5" />
          <p className="text-[10px] text-muted-foreground">
            Sent {c.success_sent_count.toLocaleString()} / {c.failed_sent_count.toLocaleString()} failed · Delivered {c.success_delivery_count.toLocaleString()} / {c.failed_delivery_count.toLocaleString()} failed
          </p>
        </div>
      </td>
      <td className="px-5 py-3.5 text-muted-foreground text-xs">
        {c.created_at ? formatDistanceToNow(new Date(c.created_at), { addSuffix: true }) : "—"}
      </td>
      <td className="px-5 py-3.5 text-muted-foreground text-xs">
        {nextRun ? (
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDistanceToNow(new Date(nextRun), { addSuffix: true })}
          </div>
        ) : "—"}
      </td>
      <td className="px-5 py-3.5">
        <div className="flex gap-1">
          <ReadinessIndicator ok={hasSchedule} label="S" />
          <ReadinessIndicator ok={hasAudience} label="A" />
          <ReadinessIndicator ok={hasContent} label="C" />
        </div>
      </td>
      <td className="px-5 py-3.5">
        <div className="flex gap-1 justify-end">
          <Link to={`/campaigns/${c.id}`}>
            <Button variant="ghost" size="icon" className="h-8 w-8"><Eye className="h-3.5 w-3.5" /></Button>
          </Link>
          <Link to={`/campaigns/${c.id}/edit`}>
            <Button variant="ghost" size="icon" className="h-8 w-8"><Pencil className="h-3.5 w-3.5" /></Button>
          </Link>
          {c.can_start && (
            <Button variant="ghost" size="icon" className="h-8 w-8 text-emerald-600 hover:text-emerald-700" onClick={() => triggerAction("start")} title="Start">
              <Play className="h-3.5 w-3.5" />
            </Button>
          )}
          {c.can_pause && (
            <Button variant="ghost" size="icon" className="h-8 w-8 text-amber-600 hover:text-amber-700" onClick={() => triggerAction("pause")} title="Pause">
              <Pause className="h-3.5 w-3.5" />
            </Button>
          )}
          {c.can_stop && (
            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => triggerAction("stop")} title="Stop">
              <Square className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => triggerAction("delete")} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function CampaignGridCard({ campaign: c, onAction }: { campaign: ApiCampaign; onAction: (a: PendingAction) => void }) {
  const channels = Array.isArray(c.channels) ? c.channels : Object.values(c.channels || {});
  const progressPercent = (c as any).progress_percent ?? 0;
  const totalMessages = (c as any).total_messages ?? 0;
  const totalProcessed = (c as any).total_processed ?? 0;
  const triggerAction = (type: ActionType) => onAction({ type, campaignId: c.id, campaignName: c.name });

  return (
    <Card className="flex min-h-[220px] flex-col shadow-card">
      <CardContent className="flex flex-1 flex-col gap-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Link to={`/campaigns/${c.id}`} className="font-semibold hover:text-primary">{c.name}</Link>
            <p className="mt-1 text-xs text-muted-foreground">Sender {c.sender_id || "—"}</p>
          </div>
          <Badge className={`${STATUS_STYLES[c.status] || STATUS_STYLES.draft} shrink-0 border text-xs`}>
            {(c as any).status_display || c.status}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-1">
          {channels.map((channel: string) => (
            <Badge key={channel} variant="secondary" className="text-xs">
              {channel === "sms" ? "SMS" : channel === "app_notification" ? "App" : channel}
            </Badge>
          ))}
          {c.execution_status_display && <Badge variant="outline" className="text-xs">{c.execution_status_display}</Badge>}
        </div>
        <div className="mt-auto space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{totalProcessed.toLocaleString()} / {totalMessages.toLocaleString()} processed</span>
            <span>{progressPercent.toFixed(0)}%</span>
          </div>
          <Progress value={progressPercent} className="h-1.5" />
          <p className="text-[10px] text-muted-foreground">
            Sent {c.success_sent_count.toLocaleString()} / {c.failed_sent_count.toLocaleString()} failed · Delivered {c.success_delivery_count.toLocaleString()} / {c.failed_delivery_count.toLocaleString()} failed
          </p>
        </div>
        <div className="flex items-center justify-between border-t pt-3">
          <span className="text-xs text-muted-foreground">
            {c.created_at ? formatDistanceToNow(new Date(c.created_at), { addSuffix: true }) : "—"}
          </span>
          <div className="flex gap-1">
            <Link to={`/campaigns/${c.id}`}><Button variant="ghost" size="icon" className="h-8 w-8" title="View"><Eye className="h-3.5 w-3.5" /></Button></Link>
            <Link to={`/campaigns/${c.id}/edit`}><Button variant="ghost" size="icon" className="h-8 w-8" title="Edit"><Pencil className="h-3.5 w-3.5" /></Button></Link>
            {c.can_start && <Button variant="ghost" size="icon" className="h-8 w-8" title="Start" onClick={() => triggerAction("start")}><Play className="h-3.5 w-3.5" /></Button>}
            {c.can_pause && <Button variant="ghost" size="icon" className="h-8 w-8" title="Pause" onClick={() => triggerAction("pause")}><Pause className="h-3.5 w-3.5" /></Button>}
            {c.can_stop && <Button variant="ghost" size="icon" className="h-8 w-8" title="Stop" onClick={() => triggerAction("stop")}><Square className="h-3.5 w-3.5" /></Button>}
            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="Delete" onClick={() => triggerAction("delete")}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ReadinessIndicator({ ok, label }: { ok?: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center justify-center h-5 w-5 rounded text-[10px] font-bold border ${
        ok
          ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800"
          : "bg-muted text-muted-foreground border-border"
      }`}
      title={`${label === "S" ? "Schedule" : label === "A" ? "Audience" : "Content"}: ${ok ? "Ready" : "Missing"}`}
    >
      {label}
    </span>
  );
}
