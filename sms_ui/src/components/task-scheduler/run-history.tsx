import { useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/task-scheduler/status-badge";
import { cn } from "@/lib/utils";
import { actions, fmtDuration, fmtTime, useScheduler } from "@/lib/task-scheduler/store";
import { schedulerApi } from "@/lib/task-scheduler/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const LEVELS = ["INFO", "WARN", "ERROR"] as const;
const levelTone = { INFO: "text-blue-600", WARN: "text-amber-600", ERROR: "text-destructive" };

export function RunHistory({
  scheduleId,
  initialRun,
  onRunSelect,
}: {
  scheduleId?: string;
  initialRun?: string;
  onRunSelect?: (runId: string) => void;
}) {
  const allRuns = useScheduler((s) => s.runs);
  const schedules = useScheduler((s) => s.schedules);
  const runs = useMemo(
    () => (scheduleId ? allRuns.filter((r) => r.scheduleId === scheduleId) : allRuns),
    [allRuns, scheduleId],
  );
  const latestRunId = runs[0]?.id;
  const selectedInitialRun =
    initialRun && runs.some((item) => item.id === initialRun) ? initialRun : undefined;
  const [selected, setSelected] = useState(() =>
    initialRun && runs.some((item) => item.id === initialRun) ? initialRun : runs[0]?.id,
  );
  const [levels, setLevels] = useState<string[]>([...LEVELS]);
  const [now, setNow] = useState(Date.now());
  const [loadingLogs, setLoadingLogs] = useState(false);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    setSelected(selectedInitialRun ?? latestRunId);
  }, [latestRunId, scheduleId, selectedInitialRun]);

  const run = runs.find((r) => r.id === selected) ?? runs[0];
  const name = (id: string) => schedules.find((s) => s.id === id)?.name ?? id;
  const lines = run?.logs.filter((l) => levels.includes(l.level)) ?? [];
  useEffect(() => {
    if (!run || run.logs.length > 0) return;
    let cancelled = false;
    setLoadingLogs(true);
    schedulerApi
      .getLogs(run.scheduleId, run.id)
      .then((logs) => {
        if (!cancelled) actions.updateRunLogs(run.scheduleId, run.id, logs);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        console.error("Unable to load run logs", error);
        toast.error(error instanceof Error ? error.message : "Unable to load run logs");
      })
      .finally(() => {
        if (!cancelled) setLoadingLogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run?.id]);

  const selectRun = (runId: string) => {
    setSelected(runId);
    onRunSelect?.(runId);
  };

  const download = () => {
    if (!run) return;
    const text = run.logs
      .map((l) => `${new Date(l.ts).toISOString()} [${l.level}] ${l.msg}`)
      .join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = `${name(run.scheduleId)}_${run.id}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Run History</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">Select a run to view its logs.</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Run ID</span>
              <Select value={run?.id ?? ""} onValueChange={selectRun} disabled={runs.length === 0}>
                <SelectTrigger className="w-44" aria-label="Select run by ID">
                  <SelectValue placeholder="Select a run" />
                </SelectTrigger>
                <SelectContent>
                  {runs.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Run ID</TableHead>
                {!scheduleId && <TableHead>Job</TableHead>}
                <TableHead>Start</TableHead>
                <TableHead>End</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-6">Trigger</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.slice(0, 40).map((r) => (
                <TableRow
                  key={r.id}
                  onClick={() => selectRun(r.id)}
                  className={cn(
                    "cursor-pointer",
                    r.id === run?.id && "bg-accent/60 hover:bg-accent/60",
                  )}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && selectRun(r.id)}
                  aria-selected={r.id === run?.id}
                >
                  <TableCell className="pl-6 font-mono text-xs">{r.id}</TableCell>
                  {!scheduleId && (
                    <TableCell className="font-mono text-sm">{name(r.scheduleId)}</TableCell>
                  )}
                  <TableCell className="text-sm">{fmtTime(r.start)}</TableCell>
                  <TableCell className="text-sm">{fmtTime(r.end)}</TableCell>
                  <TableCell className="text-sm tabular-nums">
                    {fmtDuration((r.end ?? now) - r.start)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="pr-6">
                    <Badge variant="outline">{r.trigger}</Badge>
                  </TableCell>
                </TableRow>
              ))}
              {runs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                    No runs yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="text-base">Logs</CardTitle>
            {run && <p className="mt-1 font-mono text-xs text-muted-foreground">{run.id}</p>}
          </div>
          <div className="flex items-center gap-1">
            {LEVELS.map((l) => (
              <Button
                key={l}
                size="sm"
                variant={levels.includes(l) ? "secondary" : "ghost"}
                className="h-7 px-2 text-xs"
                aria-pressed={levels.includes(l)}
                onClick={() =>
                  setLevels((x) => (x.includes(l) ? x.filter((y) => y !== l) : [...x, l]))
                }
              >
                {l}
              </Button>
            ))}
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={download}
              aria-label="Download log"
            >
              <Download className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div
            className="h-[28rem] overflow-auto bg-sidebar p-4 font-mono text-xs leading-relaxed text-sidebar-foreground"
            role="log"
            aria-live="polite"
          >
            {lines.map((l, i) => (
              <div key={i}>
                <span className="text-sidebar-foreground/50">
                  {new Date(l.ts).toLocaleTimeString()}
                </span>{" "}
                <span className={levelTone[l.level]}>[{l.level}]</span> {l.msg}
              </div>
            ))}
            {loadingLogs && <div className="text-sidebar-foreground/60">Loading logs…</div>}
            {!loadingLogs && lines.length === 0 && (
              <div className="text-sidebar-foreground/60">No logs available for this run.</div>
            )}
            {run?.status === "Running" && (
              <div className="animate-pulse text-sidebar-primary">▍ streaming…</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
