import { Link, useParams, useSearchParams } from "react-router-dom";
import { Check, ChevronDown, ChevronUp, Copy, Pencil, Play } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RunHistory } from "@/components/task-scheduler/run-history";
import { ConfirmDialog } from "@/components/task-scheduler/confirm-dialog";
import { StatusBadge } from "@/components/task-scheduler/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { actions, fmtTime, scheduleToHuman, useScheduler } from "@/lib/task-scheduler/store";
import { TaskScheduleNotFound as NotFound } from "@/pages/TaskSchedulerPages";

const RUN_DAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

export default function TaskScheduleDetail() {
  const { id = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const run = searchParams.get("run") ?? undefined;
  const s = useScheduler((st) => st.schedules.find((x) => x.id === id));
  const loaded = useScheduler((st) => st.loaded);
  const [codeExpanded, setCodeExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirm, setConfirm] = useState(false);
  if (!s && !loaded) return <div className="py-20 text-center text-muted-foreground">Loading task schedule…</div>;
  if (!s) return <NotFound />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="break-all font-mono text-2xl font-semibold">{s.name}</h1>
            <StatusBadge status={s.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {s.type} · {scheduleToHuman(s)}
            {s.scheduleType === "Cron" && (
              <>
                {" "}
                · <span className="font-mono">{s.effectiveCron || s.cron}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/task-scheduler/${encodeURIComponent(id)}/edit`}>
              <Pencil className="h-4 w-4" /> Edit
            </Link>
          </Button>
          <Button onClick={() => setConfirm(true)}>
            <Play className="h-4 w-4" /> Run now
          </Button>
        </div>
      </div>
      {s.airflowSyncError && (
        <div role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900">
          Airflow synchronization needs attention: {s.airflowSyncError}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Schedule Info</CardTitle>
          <p className="text-sm text-muted-foreground">
            Configuration and task details for this schedule.
          </p>
        </CardHeader>
        <CardContent className="space-y-5">
          <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Owner", s.owner],
              ["Owner email", s.ownerEmail],
              ["Accept notifications", s.acceptNotifications ? "Yes" : "No"],
              ["Schedule type", s.scheduleType],
              ["Timing", scheduleToHuman(s)],
              ["Timezone", s.timezone],
              [
                "Allowed weekdays",
                s.scheduleType !== "Cron"
                  ? "Not applicable"
                  : s.daysOfWeek.length
                    ? s.daysOfWeek.map((day) => RUN_DAY_NAMES[day]).join(", ")
                    : "As defined by cron",
              ],
              [
                "Run window",
                s.scheduleType === "Cron" && s.windowStart && s.windowEnd
                  ? `${s.windowStart.slice(0, 5)}–${s.windowEnd.slice(0, 5)}`
                  : s.scheduleType === "Cron"
                    ? "All day"
                    : "Not applicable",
              ],
              ["Excluded dates", s.excludedDates.length ? s.excludedDates.join(", ") : "None"],
              ["Next run", fmtTime(s.nextRun)],
              ["Last run", fmtTime(s.lastRun)],
              ["Start date", s.startDate || "—"],
              ["End date", s.endDate || "—"],
              ["Task type", s.type],
              ["Connection", s.type === "SQL" ? s.connection || "—" : "—"],
              ["Retries", `${s.retries} × ${s.retryDelay}s`],
            ].map(([label, value]) => (
              <div key={label} className="min-w-0">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="mt-1 break-words font-medium">{value}</dd>
              </div>
            ))}
          </dl>
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-medium">Code</h3>
                <p className="text-xs text-muted-foreground">
                  {s.code
                    ? `${s.code.split("\n").length.toLocaleString()} lines`
                    : "No code configured"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setCodeExpanded((expanded) => !expanded)}
                  aria-expanded={codeExpanded}
                >
                  {codeExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                  {codeExpanded ? "Hide code" : "Show code"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!s.code}
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(s.code);
                      setCopied(true);
                      toast.success("Code copied");
                      window.setTimeout(() => setCopied(false), 2000);
                    } catch (error) {
                      console.error("Unable to copy schedule code", error);
                      toast.error("Unable to copy code");
                    }
                  }}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copied" : "Copy code"}
                </Button>
              </div>
            </div>
            {codeExpanded && (
              <Textarea
                readOnly
                aria-label="Full schedule code"
                value={s.code || "No code configured."}
                className="max-h-[32rem] min-h-64 resize-y overflow-auto bg-sidebar p-4 font-mono text-xs leading-relaxed text-sidebar-foreground"
              />
            )}
          </div>
        </CardContent>
      </Card>
      <RunHistory
        key={id}
        scheduleId={id}
        initialRun={run}
        onRunSelect={(runId) => setSearchParams((previous) => {
          previous.set("run", runId);
          return previous;
        }, { replace: true })}
      />
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Run ${s.name} now?`}
        description="This triggers an immediate manual run."
        confirmText="Run now"
        onConfirm={async () => {
          try {
            await actions.runNow(id);
            setConfirm(false);
            toast.success(`Triggered ${s.name}`);
          } catch (error) {
            console.error("Unable to trigger schedule", error);
            toast.error(error instanceof Error ? error.message : "Unable to trigger schedule");
          }
        }}
      />
    </div>
  );
}
