import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Plus,
  Search,
  Pencil,
  Play,
  Pause,
  PlayCircle,
  Trash2,
  FileText,
  ArrowUpDown,
  History,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/task-scheduler/status-badge";
import { ConfirmDialog } from "@/components/task-scheduler/confirm-dialog";
import {
  useScheduler,
  actions,
  scheduleToHuman,
  fmtTime,
  type Schedule,
} from "@/lib/task-scheduler/store";

type SortKey = "name" | "nextRun" | "lastRun";
type Pending = { kind: "run" | "delete" | "bulkDelete"; items: Schedule[] } | null;

export function SchedulesPage() {
  const schedules = useScheduler((s) => s.schedules);
  const hasSchedulesNeedingSync = schedules.some(
    (schedule) => schedule.status === "Pending" || Boolean(schedule.airflowSyncError),
  );
  useEffect(() => {
    if (!hasSchedulesNeedingSync) return;
    void actions.refreshSchedules();
    const timer = window.setInterval(() => void actions.refreshSchedules(), 15_000);
    const refreshOnFocus = () => void actions.refreshSchedules();
    window.addEventListener("focus", refreshOnFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [hasSchedulesNeedingSync]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: "name", asc: true });
  const [sel, setSel] = useState<string[]>([]);
  const [pending, setPending] = useState<Pending>(null);

  const rows = useMemo(() => {
    const term = q.toLowerCase();
    return schedules
      .filter(
        (s) =>
          !term ||
          s.name.toLowerCase().includes(term) ||
          s.owner.toLowerCase().includes(term) ||
          s.ownerEmail.toLowerCase().includes(term),
      )
      .filter((s) => status === "all" || s.status === status)
      .sort((a, b) => {
        const av = a[sort.key] ?? Infinity,
          bv = b[sort.key] ?? Infinity;
        const c = av < bv ? -1 : av > bv ? 1 : 0;
        return sort.asc ? c : -c;
      });
  }, [schedules, q, status, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, asc: s.key === key ? !s.asc : true }));
  const allSel = rows.length > 0 && rows.every((r) => sel.includes(r.id));
  const SortBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <Button
      variant="ghost"
      size="sm"
      className="h-auto p-0 text-muted-foreground hover:text-foreground"
      onClick={() => toggleSort(k)}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <ArrowUpDown className="h-3 w-3" />
    </Button>
  );

  const confirm = async () => {
    if (!pending) return;
    try {
      if (pending.kind === "run") {
        await actions.runNow(pending.items[0].id);
        toast.success(`Triggered ${pending.items[0].name}`);
      } else {
        const ids = pending.items.map((i) => i.id);
        await actions.remove(ids);
        setSel((s) => s.filter((x) => !ids.includes(x)));
        toast.success(`Deleted ${ids.length} schedule${ids.length > 1 ? "s" : ""}`);
      }
      setPending(null);
    } catch (error) {
      console.error("Schedule action failed", error);
      toast.error(error instanceof Error ? error.message : "Schedule action failed");
    }
  };

  return (
    <TooltipProvider>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Schedules</h1>
            <p className="text-sm text-muted-foreground">
              {rows.length} of {schedules.length} schedules
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to="/task-scheduler/runs">
                <History className="h-4 w-4" /> Run History
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/task-scheduler/upcoming">
                <CalendarClock className="h-4 w-4" /> Upcoming Schedules
              </Link>
            </Button>
            <Button asChild>
              <Link to="/task-scheduler/new">
                <Plus className="h-4 w-4" /> New Schedule
              </Link>
            </Button>
          </div>
        </div>

        <section className="min-w-0 space-y-4" aria-labelledby="all-schedules-heading">
          <h2 id="all-schedules-heading" className="text-base font-semibold">
            All Schedules
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search name, owner, email"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-8"
                aria-label="Search schedules"
              />
            </div>
            <FilterSelect
              label="Status"
              value={status}
              onChange={setStatus}
              options={["Active", "Paused", "Failed", "Pending", "Draft"]}
            />
            {sel.length > 0 && (
              <div className="ml-auto flex items-center gap-2">
                <span className="text-sm text-muted-foreground">{sel.length} selected</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    try {
                      await actions.setPaused(sel, true);
                      toast.success(`Paused ${sel.length} schedules`);
                    } catch (error) {
                      console.error("Unable to pause schedules", error);
                      toast.error(
                        error instanceof Error ? error.message : "Unable to pause schedules",
                      );
                    }
                  }}
                >
                  <Pause className="h-4 w-4" /> Pause
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() =>
                    setPending({
                      kind: "bulkDelete",
                      items: schedules.filter((s) => sel.includes(s.id)),
                    })
                  }
                >
                  <Trash2 className="h-4 w-4" /> Delete
                </Button>
              </div>
            )}
          </div>

          <div className="overflow-x-auto rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      aria-label="Select all"
                      checked={allSel}
                      onCheckedChange={(v) => setSel(v ? rows.map((r) => r.id) : [])}
                    />
                  </TableHead>
                  <TableHead>
                    <SortBtn k="name" label="Name" />
                  </TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>
                    <SortBtn k="lastRun" label="Last Run" />
                  </TableHead>
                  <TableHead>
                    <SortBtn k="nextRun" label="Next Run" />
                  </TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((s) => (
                  <TableRow key={s.id} data-state={sel.includes(s.id) ? "selected" : undefined}>
                    <TableCell>
                      <Checkbox
                        aria-label={`Select ${s.name}`}
                        checked={sel.includes(s.id)}
                        onCheckedChange={(v) =>
                          setSel((x) => (v ? [...x, s.id] : x.filter((i) => i !== s.id)))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/task-scheduler/${encodeURIComponent(s.id)}`}
                        className="font-mono text-sm font-medium hover:text-primary hover:underline"
                      >
                        {s.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{s.type}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{scheduleToHuman(s)}</div>
                      {s.scheduleType === "Cron" && (
                        <div className="font-mono text-xs text-muted-foreground">
                          {s.effectiveCron || s.cron}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{s.owner}</TableCell>
                    <TableCell>
                      <StatusBadge status={s.status} />
                      {s.airflowSyncError && (
                        <p className="mt-1 max-w-44 truncate text-xs text-amber-700" title={s.airflowSyncError}>
                          Airflow sync needs attention
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{fmtTime(s.lastRun)}</div>
                      {s.lastStatus && <StatusBadge status={s.lastStatus} />}
                    </TableCell>
                    <TableCell className="text-sm">{fmtTime(s.nextRun)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-0.5">
                        <IconAction
                          label="Edit"
                          asLink={
                            <Link to={`/task-scheduler/${encodeURIComponent(s.id)}/edit`}>
                              <Pencil className="h-4 w-4" />
                            </Link>
                          }
                        />
                        <IconAction
                          label="Run now"
                          onClick={() => setPending({ kind: "run", items: [s] })}
                        >
                          <Play className="h-4 w-4" />
                        </IconAction>
                        <IconAction
                          label={s.status === "Paused" ? "Resume" : "Pause"}
                          onClick={async () => {
                            try {
                              await actions.setPaused([s.id], s.status !== "Paused");
                              toast.success(
                                `${s.status === "Paused" ? "Resumed" : "Paused"} ${s.name}`,
                              );
                            } catch (error) {
                              console.error("Unable to change schedule status", error);
                              toast.error(
                                error instanceof Error
                                  ? error.message
                                  : "Unable to change schedule status",
                              );
                            }
                          }}
                        >
                          {s.status === "Paused" ? (
                            <PlayCircle className="h-4 w-4" />
                          ) : (
                            <Pause className="h-4 w-4" />
                          )}
                        </IconAction>
                        <IconAction
                          label="View details and logs"
                          asLink={
                            <Link to={`/task-scheduler/${encodeURIComponent(s.id)}`}>
                              <FileText className="h-4 w-4" />
                            </Link>
                          }
                        />
                        <IconAction
                          label="Delete"
                          onClick={() => setPending({ kind: "delete", items: [s] })}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </IconAction>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                      No schedules match your filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </section>

        <ConfirmDialog
          open={!!pending}
          onOpenChange={(o) => !o && setPending(null)}
          title={
            pending?.kind === "run"
              ? `Run ${pending.items[0].name} now?`
              : `Delete ${pending?.items.length === 1 ? pending.items[0].name : `${pending?.items.length} schedules`}?`
          }
          description={
            pending?.kind === "run"
              ? "This triggers an immediate manual run outside the schedule."
              : "This permanently removes the schedule and its run history."
          }
          confirmText={pending?.kind === "run" ? "Run now" : "Delete"}
          destructive={pending?.kind !== "run"}
          typeToConfirm={
            pending?.kind === "delete"
              ? pending.items[0].name
              : pending?.kind === "bulkDelete"
                ? "DELETE"
                : undefined
          }
          onConfirm={confirm}
        />
      </div>
    </TooltipProvider>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-32" aria-label={`Filter by ${label}`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All {label.toLowerCase()}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function IconAction({
  label,
  onClick,
  children,
  asLink,
}: {
  label: string;
  onClick?: () => void;
  children?: React.ReactNode;
  asLink?: React.ReactElement;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {asLink ? (
          <Button variant="ghost" size="icon" className="h-8 w-8" asChild aria-label={label}>
            {asLink}
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClick}
            aria-label={label}
          >
            {children}
          </Button>
        )}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function UpcomingSchedulesPage() {
  const schedules = useScheduler((s) => s.schedules);
  const upcoming = schedules
    .filter((s) => s.nextRun !== undefined && s.status !== "Paused" && s.status !== "Draft")
    .sort((a, b) => (a.nextRun ?? Infinity) - (b.nextRun ?? Infinity));
  return (
    <section className="space-y-4" aria-labelledby="upcoming-schedules-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            id="upcoming-schedules-heading"
            className="flex items-center gap-2 text-2xl font-semibold tracking-tight"
          >
            <CalendarClock className="h-5 w-5 text-blue-600" />
            Upcoming Schedules
          </h1>
          <p className="text-sm text-muted-foreground">
            {upcoming.length} schedules have a future run planned.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/task-scheduler">All Schedules</Link>
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Schedule</TableHead>
              <TableHead className="text-right">Next Run</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {upcoming.map((schedule) => (
              <TableRow key={schedule.id}>
                <TableCell className="min-w-0">
                  <Link
                    to={`/task-scheduler/${encodeURIComponent(schedule.id)}`}
                    className="break-all font-mono text-sm font-medium hover:text-primary hover:underline"
                  >
                    {schedule.name}
                  </Link>
                  <p className="mt-1 text-xs text-muted-foreground">{scheduleToHuman(schedule)}</p>
                </TableCell>
                <TableCell className="whitespace-nowrap text-right text-sm text-blue-600">
                  {fmtTime(schedule.nextRun)}
                </TableCell>
              </TableRow>
            ))}
            {upcoming.length === 0 && (
              <TableRow>
                <TableCell colSpan={2} className="py-10 text-center text-muted-foreground">
                  No upcoming schedules.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
